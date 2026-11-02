#!/usr/bin/env python3
"""
Andrenalina - 3 Días: configura las URLs de AceStream y descarga las tablas
de eventos (incluida la columna "Eventos Acestream").

Ficheros que genera (en el directorio actual, pensado para la raíz del repo):
  - elcano.json           copia del hashes.json de Elcano
  - ezdakit.m3u           lista de canales generada a partir de elcano.json
  - eventos.json          tablas extraídas de la web
  - ezdakit_eventos.m3u   lista de eventos generada a partir de eventos.json

Pasos que replica en la web:
  1. Abrir la web (y aceptar el EULA, si ACCEPT_EULA=yes).
  2. Abrir "Configuración" si el panel está cerrado.
  3. Escribir la URL del hashes.json en #urlsInput.
  4. Pulsar #btnSaveUrls ("Guardar y Recargar").
  5. Esperar a que se rellene la columna y extraer las tablas.
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

SITE_URL = os.getenv("SITE_URL", "https://kiroideuno.pages.gay")
ACESTREAM_JSON_URL = os.getenv(
    "ACESTREAM_JSON_URL",
    "https://tokyo.elcano-ipfs.workers.dev/"
    "k51qzi5uqu5dh5qej4b9wlcr5i6vhc7rcfkekhrxqek5c9lk6gdaiik820fecs/hashes.json",
)
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "eventos.json")
ELCANO_FILE = os.getenv("ELCANO_FILE", "elcano.json")
CHANNELS_M3U = os.getenv("CHANNELS_M3U", "ezdakit.m3u")
EVENTS_M3U = os.getenv("EVENTS_M3U", "ezdakit_eventos.m3u")
# URL con la que se genera cada entrada de la lista de eventos ({hash} se sustituye)
EVENTS_URL_TEMPLATE = os.getenv(
    "EVENTS_URL_TEMPLATE", "http://127.0.0.1:6878/ace/getstream?id={hash}"
)
CHANNELS_URL_TEMPLATE = os.getenv(
    "CHANNELS_URL_TEMPLATE", "http://127.0.0.1:6878/ace/getstream?id={hash}"
)
TZ = ZoneInfo(os.getenv("TZ_NAME", "Europe/Madrid"))
DEBUG_DIR = os.getenv("DEBUG_DIR", "debug")
WAIT_FILL_SECONDS = int(os.getenv("WAIT_FILL_SECONDS", "90"))
ACCEPT_EULA = os.getenv("ACCEPT_EULA", "no").strip().lower() == "yes"
ACESTREAM_COLUMN = "Eventos Acestream"

TABLE_IDS = ["tablaAyer", "tablaHoy", "tablaManana", "tablaPasado", "tablaAcestream"]

# Tablas con eventos por día -> desplazamiento en días respecto a hoy.
# (Quita "tablaAyer" si no quieres eventos ya pasados en la lista.)
DAY_OFFSETS = {"tablaAyer": -1, "tablaHoy": 0, "tablaManana": 1, "tablaPasado": 2}
WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# Nombres posibles (sin acentos, minúsculas) de las columnas de las tablas
COL_TIME = ["hora", "horario", "time"]
COL_COMPETITION = ["competicion", "torneo", "campeonato", "liga"]
COL_EVENT = ["evento", "partido", "encuentro"]

M3U_HEADER = (
    '#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml,'
    "https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz,"
    'https://raw.githubusercontent.com/davidmuma/EPG_dobleM/master/guiatv.xml" refresh="3600"',
    "#EXTVLCOPT:network-caching=1000",
    "",
)
HASH_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40}(?![0-9a-fA-F])")

EXTRACT_JS = """
(ids) => {
  const clean = s => (s || "").replace(/\\s+/g, " ").trim();
  const out = [];
  for (const id of ids) {
    const table = document.getElementById(id);
    if (!table) continue;
    const visible = getComputedStyle(table).display !== "none";

    // Título: el <h2 id="titulo..."> correspondiente
    const h2 = document.getElementById("titulo" + id.replace(/^tabla/, ""));
    const titulo = h2 ? clean(h2.textContent) : "";

    const headers = [...table.querySelectorAll("thead th")].map(th => clean(th.textContent));
    const rows = [...table.querySelectorAll("tbody tr")].map(tr => {
      const row = {};
      const links = {};
      [...tr.children].forEach((td, i) => {
        const key = headers[i] || ("col_" + i);
        // innerText respeta los <br> como saltos de línea
        row[key] = (td.innerText || "").split("\\n").map(clean).filter(Boolean).join(" | ");
        const found = [...td.querySelectorAll("a[href]")].map(a => ({
          texto: clean(a.textContent),
          href: a.getAttribute("href"),
        }));
        if (found.length) links[key] = found;
      });
      if (Object.keys(links).length) row["_enlaces"] = links;
      return row;
    });
    out.push({ id, titulo, visible, columnas: headers, filas: rows });
  }
  return out;
}
"""


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def save_debug(page, name):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    try:
        page.screenshot(path=os.path.join(DEBUG_DIR, f"{name}.png"), full_page=True)
        with open(os.path.join(DEBUG_DIR, f"{name}.html"), "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception as e:  # noqa: BLE001
        log(f"No se pudo guardar debug '{name}': {e}")


def handle_eula(page):
    """Si aparece el EULA, lo acepta solo cuando ACCEPT_EULA=yes."""
    page.wait_for_function(
        """() => {
            const o = document.getElementById('eula-overlay');
            const c = document.getElementById('contenido-app');
            const eulaVisible = o && getComputedStyle(o).display !== 'none';
            const appVisible = c && !c.hidden && getComputedStyle(c).display !== 'none';
            return eulaVisible || appVisible;
        }""",
        timeout=30000,
    )
    if not page.locator("#eula-overlay").is_visible():
        log("EULA ya aceptado o no necesario")
        return

    if not ACCEPT_EULA:
        save_debug(page, "eula")
        log(
            "La web muestra un EULA. Lee los términos y, si los aceptas, "
            "define ACCEPT_EULA=yes (en el workflow) para que el script lo acepte."
        )
        sys.exit(2)

    frase = page.locator("#eula-frase-label").inner_text().strip()
    log(f"Aceptando EULA (frase: {frase!r})")
    page.locator("#eula-confirm-input").fill(frase)
    page.locator("#eula-accept-btn").click()
    page.wait_for_function(
        "() => { const c = document.getElementById('contenido-app'); return c && !c.hidden; }",
        timeout=15000,
    )


def acestream_filled(tables):
    """True si alguna celda de la columna Acestream tiene algo más que '-'."""
    for t in tables:
        for fila in t["filas"]:
            valor = fila.get(ACESTREAM_COLUMN, "").strip()
            if valor and valor != "-":
                return True
    return False


# ----------------------------------------------------------------------------
# Elcano: descarga de hashes.json y generación de ezdakit.m3u
# ----------------------------------------------------------------------------
def fetch_elcano():
    """Descarga el hashes.json de Elcano (con reintentos) y lo devuelve como dict."""
    req = urllib.request.Request(
        ACESTREAM_JSON_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ezdakit-scraper)"},
    )
    last = None
    for intento in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            if not isinstance(data.get("hashes"), list):
                raise ValueError("el JSON no contiene la lista 'hashes'")
            return data
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"Descarga de elcano.json fallida (intento {intento}/3): {e}")
            time.sleep(3 * intento)
    raise RuntimeError(f"No se pudo descargar {ACESTREAM_JSON_URL}: {last}")


def quality_label(height):
    if height >= 2160:
        return "UHD"
    if height >= 1080:
        return "FHD"
    if height >= 720:
        return "HD"
    return "SD"


TITLE_RE = re.compile(r"^(?P<base>.*?)\s+(?P<res>\d{3,4})p\s*(?P<stars>\**)\s*$")


def split_title(title):
    """'DAZN 2 1080p **' -> ('DAZN 2', 'FHD', '**')."""
    title = (title or "").strip()
    m = TITLE_RE.match(title)
    if not m:
        return title, "", ""
    return m["base"].strip(), quality_label(int(m["res"])), m["stars"]


def attr(value):
    """Valor seguro para un atributo M3U (sin comillas dobles ni saltos de línea)."""
    return re.sub(r"\s+", " ", str(value or "")).replace('"', "'").strip()


def write_m3u(path, lines):
    # Mismo formato que los ficheros de ejemplo: saltos de línea CRLF
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(list(M3U_HEADER) + lines) + "\r\n")


def build_channels_m3u(elcano, path):
    lines = []
    for item in elcano["hashes"]:
        h = (item.get("hash") or "").strip().lower()
        if not h:
            continue
        base, quality, stars = split_title(item.get("title"))
        name = base.upper()
        if stars:
            name += f" {stars}"
        if quality:
            name += f" ({quality})"
        name += f" (E-{h[:3]})"
        tvg_id = attr(item.get("tvg_id")) or "Unknown"
        group = attr(item.get("group"))
        lines.append(
            f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{attr(name)}" group-title="{group}",{name}'
        )
        lines.append(CHANNELS_URL_TEMPLATE.format(hash=h))
    write_m3u(path, lines)
    return len(lines) // 2


# ----------------------------------------------------------------------------
# Eventos: generación de ezdakit_eventos.m3u a partir de las tablas
# ----------------------------------------------------------------------------
def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).strip().lower()


def find_col(columnas, candidatos):
    """Primera columna cuyo nombre (normalizado) empieza por algún candidato."""
    for cand in candidatos:
        for c in columnas:
            if c != ACESTREAM_COLUMN and norm(c).startswith(cand):
                return c
    return None


def elcano_index(elcano):
    idx = {}
    for item in elcano.get("hashes", []):
        h = (item.get("hash") or "").strip().lower()
        if h:
            idx[h] = item
    return idx


QUALITY_RE = re.compile(r"\b(UHD|FHD|HD|SD|4K)\b", re.I)
GENERIC_LABELS = {"", "ver", "play", "acestream", "ace", "link", "enlace", "stream", "-"}


def label_from_text(texto, h):
    """Canal y calidad a partir del texto del enlace, p. ej. 'DAZN 2 (FHD)'."""
    t = texto.replace(h, "")
    q = QUALITY_RE.search(t)
    quality = q.group(1).upper() if q else ""
    t = QUALITY_RE.sub("", t)
    t = re.sub(r"[()\[\]*]", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -|:").upper()
    if norm(t) in GENERIC_LABELS:
        return "", quality
    return t, quality


def extract_streams(fila, idx):
    """Lista de (hash, canal, calidad) de la celda 'Eventos Acestream' de una fila."""
    enlaces = fila.get("_enlaces", {}).get(ACESTREAM_COLUMN, [])
    candidatos = []
    for e in enlaces:
        m = HASH_RE.search(e.get("href") or "") or HASH_RE.search(e.get("texto") or "")
        if m:
            candidatos.append((m.group(0).lower(), e.get("texto") or ""))
    if not candidatos:  # sin <a>: buscar hashes en el texto de la celda
        for parte in (fila.get(ACESTREAM_COLUMN) or "").split(" | "):
            m = HASH_RE.search(parte)
            if m:
                candidatos.append((m.group(0).lower(), parte))

    out = []
    for h, texto in candidatos:
        canal, calidad = "", ""
        if h in idx:  # 1º: el catálogo de Elcano (nombre y calidad consistentes)
            base, calidad, _ = split_title(idx[h].get("title"))
            canal = base.upper()
        if not canal:  # 2º: el texto del enlace
            canal, q2 = label_from_text(texto, h)
            calidad = calidad or q2
        out.append((h, canal or "ACESTREAM", calidad))
    return out


def clean_cell(valor):
    return re.sub(r"\s+", " ", (valor or "").replace(" | ", " ")).strip()


def collect_events(tables, idx):
    hoy = datetime.now(TZ).date()
    eventos = []
    for t in tables:
        if t["id"] not in DAY_OFFSETS:
            continue
        m_fecha = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", t.get("titulo", ""))
        if m_fecha:  # fecha que muestra la propia web en el título de la tabla
            dia = datetime(int(m_fecha[3]), int(m_fecha[2]), int(m_fecha[1])).date()
        else:  # respaldo: desplazamiento respecto a hoy
            dia = hoy + timedelta(days=DAY_OFFSETS[t["id"]])
        fecha = f"{dia.month:02d}-{dia.day:02d} ({WEEKDAYS[dia.weekday()]})"
        cols = t.get("columnas", [])
        c_hora = find_col(cols, COL_TIME)
        c_comp = find_col(cols, COL_COMPETITION)
        c_even = find_col(cols, COL_EVENT)
        if not (c_hora and c_even):
            log(f"AVISO: {t['id']}: no encuentro columnas de hora/evento en {cols}")
        for fila in t["filas"]:
            streams = extract_streams(fila, idx)
            if not streams:
                continue
            raw_hora = clean_cell(fila.get(c_hora, "")) if c_hora else ""
            m = re.search(r"\d{1,2}:\d{2}", raw_hora)
            # Sin hora numérica (p. ej. "PD" = por definir) se conserva el texto y va al final del día
            hora = m.group(0).zfill(5) if m else (raw_hora or "PD")
            evento = clean_cell(fila.get(c_even, "")) if c_even else ""
            comp = clean_cell(fila.get(c_comp, "")) if c_comp else ""
            for h, canal, calidad in streams:
                eventos.append(
                    {"dia": dia, "fecha": fecha, "hora": hora, "comp": comp or "Eventos",
                     "evento": evento or "Evento", "canal": canal, "calidad": calidad, "hash": h}
                )
    eventos.sort(key=lambda e: (e["dia"], e["hora"]))  # orden estable
    return eventos


def build_events_m3u(tables, elcano, path):
    eventos = collect_events(tables, elcano_index(elcano))
    lines, vistos = [], set()
    for e in eventos:
        clave = (e["fecha"], e["comp"], e["hora"], e["evento"], e["canal"], e["hash"])
        if clave in vistos:
            continue
        vistos.add(clave)
        name = f'{e["hora"]}-{e["evento"]} ({e["canal"]})'
        if e["calidad"]:
            name += f' ({e["calidad"]})'
        name += f' ({e["hash"][:3]})'
        group = f'{e["fecha"]} {e["comp"]}'
        lines.append(f'#EXTINF:-1 group-title="{attr(group)}" tvg-name="{attr(name)}",{name}')
        lines.append(EVENTS_URL_TEMPLATE.format(hash=e["hash"]))
    write_m3u(path, lines)
    return len(lines) // 2


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    errores = []

    # 1) elcano.json + ezdakit.m3u (no dependen de la web)
    elcano = None
    try:
        elcano = fetch_elcano()
        write_json(ELCANO_FILE, elcano)
        n = build_channels_m3u(elcano, CHANNELS_M3U)
        log(f"Guardado {ELCANO_FILE} ({len(elcano['hashes'])} hashes) y {CHANNELS_M3U} ({n} canales)")
    except Exception as e:  # noqa: BLE001
        log(f"ERROR con Elcano: {e}")
        errores.append("elcano")

    # 2) scraping de la web
    tables = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="es-ES",
            timezone_id="Europe/Madrid",
        )
        page = context.new_page()
        try:
            log(f"Abriendo {SITE_URL}")
            page.goto(SITE_URL, wait_until="domcontentloaded", timeout=60000)
            handle_eula(page)
            page.wait_for_load_state("networkidle", timeout=60000)
            save_debug(page, "01_inicial")

            # Abrir el panel de configuración si está cerrado
            if not page.locator("#urlsInput").is_visible():
                log("Abriendo panel de configuración")
                page.locator("#btnToggleConfig").click()
            page.locator("#urlsInput").wait_for(state="visible", timeout=15000)

            log("Escribiendo la URL del JSON de AceStream")
            page.locator("#urlsInput").fill(ACESTREAM_JSON_URL)
            save_debug(page, "02_url_pegada")

            log("Pulsando 'Guardar y Recargar'")
            try:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
                    page.locator("#btnSaveUrls").click()
            except PWTimeout:
                log("No se detectó navegación explícita; se continúa")

            # Tras recargar, el EULA ya está aceptado (cookie), pero por si acaso:
            handle_eula(page)
            page.wait_for_load_state("networkidle", timeout=60000)

            log(f"Esperando a que se rellene '{ACESTREAM_COLUMN}' (máx {WAIT_FILL_SECONDS}s)")
            tables = []
            deadline = time.time() + WAIT_FILL_SECONDS
            while time.time() < deadline:
                tables = page.evaluate(EXTRACT_JS, TABLE_IDS)
                if tables and acestream_filled(tables):
                    # pequeña pausa para que terminen de pintarse todas las tablas
                    time.sleep(3)
                    tables = page.evaluate(EXTRACT_JS, TABLE_IDS)
                    break
                time.sleep(2)
            else:
                log("AVISO: la columna Acestream sigue vacía tras la espera")

            save_debug(page, "03_final")
        except Exception:
            save_debug(page, "error")
            raise
        finally:
            browser.close()

    # 3) eventos.json + ezdakit_eventos.m3u (solo si la columna Acestream se rellenó,
    #    para no machacar con datos vacíos la última versión buena)
    if acestream_filled(tables):
        resultado = {
            "fuente": SITE_URL,
            "acestream_json": ACESTREAM_JSON_URL,
            "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tablas": tables,
        }
        write_json(OUTPUT_FILE, resultado)
        total = sum(len(t["filas"]) for t in tables)
        log(f"Guardado {OUTPUT_FILE}: {len(tables)} tablas, {total} filas")
        try:
            n = build_events_m3u(tables, elcano or {"hashes": []}, EVENTS_M3U)
            log(f"Guardado {EVENTS_M3U}: {n} entradas")
        except Exception as e:  # noqa: BLE001
            log(f"ERROR generando {EVENTS_M3U}: {e}")
            errores.append("m3u_eventos")
    else:
        log("La columna Acestream está vacía: no se actualizan eventos.json ni el m3u de eventos")
        errores.append("eventos")

    if errores:
        sys.exit(1)


if __name__ == "__main__":
    main()
