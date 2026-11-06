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
  3. Descargar el hashes.json directamente de IPFS (nodo local o pasarelas
     públicas, sin proxy) y escribir su URL en #urlsInput; el script intercepta
     esa petición de la web y le sirve el JSON ya descargado.
  4. Pulsar #btnSaveUrls ("Guardar y Recargar").
  5. Esperar a que se rellene la columna y extraer las tablas.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

# URLs de la web, por orden de preferencia (la segunda es un espejo de la primera).
# Se puede sobrescribir con SITE_URLS="url1,url2".
SITE_URLS = [
    u.strip()
    for u in os.getenv(
        "SITE_URLS", "https://kiroideuno.pages.gay/,https://andrenalina.wasmer.app/"
    ).split(",")
    if u.strip()
]
# --- Elcano / IPFS (acceso directo, sin proxy) ---------------------------------
# k51... es un nombre IPNS que apunta a un directorio IPFS que contiene hashes.json
ELCANO_IPNS_KEY = os.getenv(
    "ELCANO_IPNS_KEY", "k51qzi5uqu5dh5qej4b9wlcr5i6vhc7rcfkekhrxqek5c9lk6gdaiik820fecs"
)
ELCANO_FILE_PATH = os.getenv("ELCANO_FILE_PATH", "hashes.json")
IPNS_PATH = f"/ipns/{ELCANO_IPNS_KEY}/{ELCANO_FILE_PATH}"
# Segundos máximos para resolver el IPNS y leer el fichero con el nodo local
IPFS_CLI_TIMEOUT = int(os.getenv("IPFS_CLI_TIMEOUT", "60"))
# Pasarelas públicas de respaldo (ellas mismas son nodos IPFS), separadas por comas
IPFS_GATEWAYS = [
    g.strip().rstrip("/")
    for g in os.getenv("IPFS_GATEWAYS", "https://dweb.link,https://ipfs.io").split(",")
    if g.strip()
]
# Último recurso opcional (p. ej. el proxy antiguo). Vacío = no se usa ningún proxy.
ELCANO_FALLBACK_URL = os.getenv("ELCANO_FALLBACK_URL", "").strip()
# URL "virtual" que se escribe en la web. Esa petición se intercepta y se responde
# con el JSON descargado de IPFS, así la web no depende de ninguna pasarela ni proxy.
PAGE_JSON_URL = os.getenv("PAGE_JSON_URL", "https://elcano.ipfs.invalid/hashes.json")
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
TZ_NAME = os.getenv("TZ_NAME", "Europe/Madrid")
TZ = ZoneInfo(TZ_NAME)
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


def wait_idle(page, timeout=20000):
    """Espera a que la red se calme, pero no falla si nunca llega a 'idle'
    (la web puede mantener peticiones periódicas); la espera real la hace
    el bucle de lectura de tablas."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except PWTimeout:
        log("networkidle no alcanzado; se continúa")


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
def _validate_elcano(raw):
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data.get("hashes"), list) or not data["hashes"]:
        raise ValueError("el JSON no contiene una lista 'hashes' con datos")
    return data


CID_RE = re.compile(r"/ipfs/([A-Za-z0-9]+)")


def _from_ipfs_cli():
    """Lee el fichero con el nodo IPFS local (Kubo). Falla rápido si no hay demonio.
    Primero resuelve el IPNS al CID raíz actual y luego lee el fichero de ese CID,
    así el CID registrado es exactamente el del contenido que se ha leído.
    Devuelve (bytes, cid)."""
    if not shutil.which("ipfs"):
        raise RuntimeError("el binario 'ipfs' no está instalado")

    def run(*args):
        r = subprocess.run(
            ["ipfs", *args, f"--timeout={IPFS_CLI_TIMEOUT}s"],
            capture_output=True,
            timeout=IPFS_CLI_TIMEOUT + 15,
        )
        if r.returncode != 0:
            msg = r.stderr.decode("utf-8", "replace").strip()[:300]
            raise RuntimeError(msg or f"'ipfs {args[0]}' terminó con código {r.returncode}")
        return r.stdout

    resuelto = run("resolve", f"/ipns/{ELCANO_IPNS_KEY}").decode("utf-8").strip()
    m = CID_RE.search(resuelto)
    if not m:
        raise RuntimeError(f"respuesta inesperada de 'ipfs resolve': {resuelto!r}")
    cid = m.group(1)
    return run("cat", f"/ipfs/{cid}/{ELCANO_FILE_PATH}"), cid


def _cid_from_headers(headers):
    """CID raíz según las cabeceras de una pasarela (None si no lo indica)."""
    roots = (headers.get("X-Ipfs-Roots") or "").split(",")[0].strip()
    if roots:
        return roots
    etag = (headers.get("ETag") or "").strip()
    etag = etag[2:] if etag.startswith("W/") else etag
    etag = etag.strip('"')
    if etag.startswith(("Qm", "bafy", "bafk")):
        return etag
    return None


def _from_http(url, timeout=30):
    """Descarga por HTTP. Devuelve (bytes, cid_o_None)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ezdakit-scraper)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), _cid_from_headers(r.headers)


def fetch_elcano():
    """Descarga el hashes.json de Elcano directamente de IPFS.
    Orden: nodo local -> pasarelas públicas -> (opcional) ELCANO_FALLBACK_URL.
    Devuelve (datos, nombre_de_la_fuente_usada, cid_o_None)."""
    fuentes = [("nodo IPFS local", _from_ipfs_cli)]
    for gw in IPFS_GATEWAYS:
        fuentes.append((gw, lambda gw=gw: _from_http(f"{gw}{IPNS_PATH}")))
    if ELCANO_FALLBACK_URL:
        fuentes.append((ELCANO_FALLBACK_URL, lambda: _from_http(ELCANO_FALLBACK_URL)))

    rondas = 2
    for ronda in range(1, rondas + 1):
        for nombre, obtener in fuentes:
            try:
                raw, cid = obtener()
                data = _validate_elcano(raw)
                log(f"hashes.json obtenido de: {nombre} (CID: {cid or 'no indicado'})")
                return data, nombre, cid
            except Exception as e:  # noqa: BLE001
                log(f"  {nombre} (ronda {ronda}/{rondas}): {type(e).__name__}: {e}")
        if ronda < rondas:
            time.sleep(5)
    raise RuntimeError(f"No se pudo obtener {IPNS_PATH} de ninguna fuente")


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
    if not lines:
        raise ValueError("lista de canales vacía: no se sobrescribe " + path)
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
    if not lines:
        raise ValueError("ningún evento con hash: no se sobrescribe " + path)
    write_m3u(path, lines)
    return len(lines) // 2


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_if_changed(path, resultado):
    """Escribe el JSON solo si las tablas (o el CID de Elcano) han cambiado (ignora generado_utc),
    para no generar un commit en cada ejecución sin cambios reales."""
    try:
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
        cid_old, cid_new = old.get("elcano_cid"), resultado.get("elcano_cid")
        cid_cambia = bool(cid_old and cid_new and cid_old != cid_new)
        if old.get("tablas") == resultado["tablas"] and not cid_cambia:
            log(f"{path}: sin cambios en las tablas, no se reescribe")
            return False
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    write_json(path, resultado)
    return True


def scrape_site(site_url, tag, elcano):
    """Abre una URL de la web, configura el JSON de AceStream y devuelve las tablas.
    Lanza una excepción si la web no carga o no termina de rellenarse.
    La petición de la web a PAGE_JSON_URL se intercepta y se responde con `elcano`
    (descargado antes de IPFS), de modo que no hace falta proxy ni pasarela."""
    body = json.dumps(elcano, ensure_ascii=False)
    served = {"n": 0}

    def serve_json(route):
        served["n"] += 1
        route.fulfill(
            status=200,
            content_type="application/json; charset=utf-8",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
            },
            body=body,
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="es-ES",
            timezone_id=TZ_NAME,
        )
        context.route(PAGE_JSON_URL, serve_json)
        page = context.new_page()
        try:
            log(f"Abriendo {site_url}")
            page.goto(site_url, wait_until="domcontentloaded", timeout=60000)
            handle_eula(page)
            wait_idle(page)
            save_debug(page, f"{tag}_01_inicial")

            # Abrir el panel de configuración si está cerrado
            if not page.locator("#urlsInput").is_visible():
                log("Abriendo panel de configuración")
                page.locator("#btnToggleConfig").click()
            page.locator("#urlsInput").wait_for(state="visible", timeout=15000)

            log("Escribiendo la URL del JSON de AceStream")
            page.locator("#urlsInput").fill(PAGE_JSON_URL)
            save_debug(page, f"{tag}_02_url_pegada")

            log("Pulsando 'Guardar y Recargar'")
            try:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
                    page.locator("#btnSaveUrls").click()
            except PWTimeout:
                log("No se detectó navegación explícita; se continúa")

            # Tras recargar, el EULA ya está aceptado (cookie), pero por si acaso:
            handle_eula(page)
            wait_idle(page)

            log(f"Esperando a que cargue la página (máx {WAIT_FILL_SECONDS}s)")
            tables = []
            prev = None
            ready = False
            deadline = time.time() + WAIT_FILL_SECONDS
            while time.time() < deadline:
                tables = page.evaluate(EXTRACT_JS, TABLE_IDS)
                if tables_ready(tables):
                    # Carga estable: mismas filas y mismas celdas Acestream rellenas en dos lecturas seguidas
                    filled = sum(
                        1
                        for t in tables
                        for f in t["filas"]
                        if f.get(ACESTREAM_COLUMN, "").strip() not in ("", "-")
                    )
                    sig = (tuple(len(t["filas"]) for t in tables), filled)
                    if sig == prev:
                        ready = True
                        break
                    prev = sig
                else:
                    prev = None
                time.sleep(2)

            save_debug(page, f"{tag}_03_final")
            log(f"La web pidió el JSON de Elcano {served['n']} vez/veces")
            if served["n"] == 0:
                log("AVISO: la web no pidió PAGE_JSON_URL; revisa debug/ por si usa otra vía de descarga")
            if not ready:
                raise RuntimeError(
                    "la página no terminó de cargar (tablaAcestream o columna Acestream vacías)"
                )
            return tables
        except Exception:
            save_debug(page, f"{tag}_error")
            raise
        finally:
            browser.close()


def tables_ready(tables):
    """La página terminó de cargar: hay hashes en los eventos Y la última tabla
    (tablaAcestream, con todos los enlaces disponibles) ya tiene filas."""
    ultima = next((t for t in tables if t["id"] == "tablaAcestream"), None)
    return bool(ultima and ultima["filas"]) and acestream_filled(tables)


def main():
    errores = []

    # 1) elcano.json + ezdakit.m3u (se descargan de IPFS, no dependen de la web)
    elcano, elcano_src, elcano_cid = None, None, None
    try:
        elcano, elcano_src, elcano_cid = fetch_elcano()
        write_json(ELCANO_FILE, elcano)
        n = build_channels_m3u(elcano, CHANNELS_M3U)
        log(f"Guardado {ELCANO_FILE} ({len(elcano['hashes'])} hashes) y {CHANNELS_M3U} ({n} canales)")
    except Exception as e:  # noqa: BLE001
        log(f"ERROR con Elcano: {e}")
        errores.append("elcano")

    # 2) scraping de la web: se prueba cada URL hasta que una cargue por completo
    tables, site_used = [], None
    if elcano is None:
        log("Sin datos de Elcano no se puede rellenar la columna Acestream: se omite la web")
    else:
        for i, url in enumerate(SITE_URLS, 1):
            try:
                tables = scrape_site(url, f"{i}", elcano)
                site_used = url
                break
            except Exception as e:  # noqa: BLE001
                log(f"ERROR con {url}: {type(e).__name__}: {e}")
                if i < len(SITE_URLS):
                    log("Probando la siguiente URL de respaldo")
        if site_used is None:
            log("No se pudo cargar ninguna de las URLs de la web")

    # 3) eventos.json + ezdakit_eventos.m3u (solo si la página terminó de cargar,
    #    para no machacar con datos vacíos la última versión buena)
    if tables_ready(tables):
        try:
            # Primero el M3U (falla si no hay entradas); solo entonces eventos.json
            n = build_events_m3u(tables, elcano or {"hashes": []}, EVENTS_M3U)
            log(f"Guardado {EVENTS_M3U}: {n} entradas")
            resultado = {
                "fuente": site_used,
                "acestream_json": IPNS_PATH,
                "elcano_fuente": elcano_src,
                "elcano_cid": elcano_cid,
                "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "tablas": tables,
            }
            total = sum(len(t["filas"]) for t in tables)
            if write_if_changed(OUTPUT_FILE, resultado):
                log(f"Guardado {OUTPUT_FILE}: {len(tables)} tablas, {total} filas")
        except Exception as e:  # noqa: BLE001
            log(f"ERROR generando eventos (se conservan los ficheros anteriores): {e}")
            errores.append("eventos")
    else:
        log("La carga no se completó: no se actualizan eventos.json ni el m3u de eventos")
        errores.append("eventos")

    if errores:
        sys.exit(1)


if __name__ == "__main__":
    main()
