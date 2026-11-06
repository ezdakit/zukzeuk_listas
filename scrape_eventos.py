#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# --- Configuración IPFS (Mantenida intacta) ---
ELCANO_IPNS_KEY = os.getenv("ELCANO_IPNS_KEY", "k51qzi5uqu5dh5qej4b9wlcr5i6vhc7rcfkekhrxqek5c9lk6gdaiik820fecs")
ELCANO_FILE_PATH = os.getenv("ELCANO_FILE_PATH", "hashes.json")
IPNS_PATH = f"/ipns/{ELCANO_IPNS_KEY}/{ELCANO_FILE_PATH}"
IPFS_CLI_TIMEOUT = int(os.getenv("IPFS_CLI_TIMEOUT", "60"))
IPFS_GATEWAYS = [
    g.strip().rstrip("/")
    for g in os.getenv("IPFS_GATEWAYS", "https://dweb.link,https://ipfs.io,https://w3s.link,https://gateway.pinata.cloud").split(",")
    if g.strip()
]
ELCANO_FALLBACK_URL = os.getenv("ELCANO_FALLBACK_URL", "").strip()

# --- Ficheros ---
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "eventos.json")
ELCANO_FILE = os.getenv("ELCANO_FILE", "elcano.json")
CHANNELS_M3U = os.getenv("CHANNELS_M3U", "ezdakit.m3u")
EVENTS_M3U = os.getenv("EVENTS_M3U", "ezdakit_eventos.m3u")
EVENTS_URL_TEMPLATE = "http://127.0.0.1:6878/ace/getstream?id={hash}"
CHANNELS_URL_TEMPLATE = "http://127.0.0.1:6878/ace/getstream?id={hash}"

FUTBOL_URL = os.getenv("FUTBOL_URL", "https://www.futbolenlatv.es/deporte")
EQUIVALENCIAS_URL = os.getenv("EQUIVALENCIAS_URL", "https://kiroideuno.pages.gay/equivalencias_canales.json")
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

M3U_HEADER = (
    '#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml,'
    "https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz,"
    'https://raw.githubusercontent.com/davidmuma/EPG_dobleM/master/guiatv.xml" refresh="3600"',
    "#EXTVLCOPT:network-caching=1000",
    "",
)


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).strip().lower()


def attr(value):
    return re.sub(r"\s+", " ", str(value or "")).replace('"', "'").strip()


def write_m3u(path, lines):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(list(M3U_HEADER) + lines) + "\r\n")


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# --- Funciones de Canales y Calidad ---
def quality_label(height):
    if height >= 2160: return "UHD"
    if height >= 1080: return "FHD"
    if height >= 720: return "HD"
    return "SD"


TITLE_RE = re.compile(r"^(?P<base>.*?)\s+(?P<res>\d{3,4})p\s*(?P<stars>\**)\s*$")


def split_title(title):
    title = (title or "").strip()
    m = TITLE_RE.match(title)
    if not m: return title, "", ""
    return m["base"].strip(), quality_label(int(m["res"])), m["stars"]


# --- Descarga IPFS (Mantenida intacta) ---
def _validate_elcano(raw):
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data.get("hashes"), list) or not data["hashes"]:
        raise ValueError("el JSON no contiene una lista 'hashes' con datos")
    return data


def _from_ipfs_cli():
    if not shutil.which("ipfs"): raise RuntimeError("el binario 'ipfs' no está instalado")

    def run(*args):
        r = subprocess.run(["ipfs", *args, f"--timeout={IPFS_CLI_TIMEOUT}s"], capture_output=True, timeout=IPFS_CLI_TIMEOUT + 15)
        if r.returncode != 0: raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:300])
        return r.stdout

    resuelto = run("resolve", f"/ipns/{ELCANO_IPNS_KEY}").decode("utf-8").strip()
    cid = re.search(r"/ipfs/([A-Za-z0-9]+)", resuelto).group(1)
    return run("cat", f"/ipfs/{cid}/{ELCANO_FILE_PATH}"), cid


def _from_http(url, timeout=30):
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), None


def fetch_elcano():
    fuentes = [("nodo IPFS local", _from_ipfs_cli)]
    for gw in IPFS_GATEWAYS: fuentes.append((gw, lambda gw=gw: _from_http(f"{gw}{IPNS_PATH}")))
    if ELCANO_FALLBACK_URL: fuentes.append((ELCANO_FALLBACK_URL, lambda: _from_http(ELCANO_FALLBACK_URL)))
    rondas = 2
    for ronda in range(1, rondas + 1):
        for nombre, obtener in fuentes:
            try:
                raw, cid = obtener()
                data = _validate_elcano(raw)
                log(f"hashes.json obtenido de: {nombre}")
                return data, nombre, cid
            except Exception as e:
                log(f"  {nombre} (ronda {ronda}/{rondas}): {type(e).__name__}: {e}")
        if ronda < rondas: time.sleep(5)
    raise RuntimeError("No se pudo obtener hashes.json de ninguna fuente")


def build_channels_m3u(elcano, path):
    lines = []
    for item in elcano["hashes"]:
        h = (item.get("hash") or "").strip().lower()
        if not h: continue
        base, quality, stars = split_title(item.get("title"))
        name = f"{base.upper()} {stars} ({quality}) (E-{h[:3]})".replace("  ", " ").strip()
        tvg_id, group = attr(item.get("tvg_id", "Unknown")), attr(item.get("group", ""))
        lines.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{attr(name)}" group-title="{group}",{name}')
        lines.append(CHANNELS_URL_TEMPLATE.format(hash=h))
    if lines: write_m3u(path, lines)
    return len(lines) // 2


# ============================================================================
# Agenda de futbolenlatv.es
# ============================================================================
DATE_RE = re.compile(r"(\d{2}/\d{2}/\d{4})")
TIME_RE = re.compile(r"\b([0-2]?\d:[0-5]\d)\b")


def _txt(node):
    """Texto de un nodo con espacios normalizados (los <br> cuentan como espacio)."""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def _limpiar_canal(nombre):
    """Quita restos tras el último ')' (p.ej. ' HD') y descarta guiones/vacíos."""
    nombre = re.sub(r"\s+", " ", nombre or "").strip()
    if nombre in ("", "-", "–"):
        return ""
    if ")" in nombre:
        nombre = nombre[: nombre.rfind(")") + 1].strip()
    return nombre


def extraer_canales(celda):
    """Lista de canales de la última celda de la fila (uno por <li> o por línea)."""
    items = []
    lis = celda.select("li")
    if lis:
        for li in lis:
            items.append(li.get("title") or _txt(li))
    else:
        # Cada <br> separa un canal; el resto de etiquetas (enlaces, spans) se concatenan
        for br in celda.find_all("br"):
            br.replace_with("\n")
        items = celda.get_text("").split("\n")
    vistos, canales = set(), []
    for it in items:
        c = _limpiar_canal(it)
        if c and c not in vistos:
            vistos.add(c)
            canales.append(c)
    return canales


def parse_agenda(html):
    """
    Cada fila de evento tiene: hora | competición | evento (local y visitante,
    o una sola celda si no hay rival) | canales.
    La fecha sale de la fila de cabecera de cada tabla ("Partidos de hoy ..., dd/mm/aaaa").
    """
    soup = BeautifulSoup(html, "html.parser")
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%d/%m/%Y")
    fecha_actual = hoy
    eventos = []

    for tr in soup.find_all("tr"):
        celdas = tr.find_all(["td", "th"], recursive=False)
        if not celdas:
            continue

        # Fila de cabecera con la fecha
        es_cabecera = "cabeceraTabla" in (tr.get("class") or [])
        if es_cabecera or (len(celdas) == 1 and DATE_RE.search(_txt(celdas[0]))):
            m = DATE_RE.search(_txt(tr))
            if m:
                fecha_actual = m.group(1)
            continue

        if len(celdas) < 4:
            continue

        m_hora = TIME_RE.search(_txt(celdas[0]))
        if not m_hora:
            continue
        hora = m_hora.group(1)

        competicion = _txt(celdas[1])
        partes = [t for t in (_txt(c) for c in celdas[2:-1]) if t]
        canales = extraer_canales(celdas[-1])
        if not partes:
            continue

        evento = {
            "fecha": fecha_actual,
            "hora": hora,
            "competicion": competicion,
            "partido": " vs ".join(partes),
            "canales": canales,
        }
        if len(partes) == 2:
            evento["local"], evento["visitante"] = partes
        eventos.append(evento)

    return eventos


def scrape_futbolenlatv():
    r = requests.get(FUTBOL_URL, headers=HTTP_HEADERS, timeout=30)
    r.raise_for_status()
    eventos = parse_agenda(r.text)
    por_fecha = {}
    for e in eventos:
        por_fecha[e["fecha"]] = por_fecha.get(e["fecha"], 0) + 1
    log("Eventos por fecha: " + ", ".join(f"{f}: {n}" for f, n in por_fecha.items()))
    return eventos


# ============================================================================
# Equivalencias de canales  {canal de la web: [nombres de canal en Elcano]}
# ============================================================================
def fetch_equivalencias():
    try:
        r = requests.get(EQUIVALENCIAS_URL, headers=HTTP_HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log(f"Aviso: No se pudo cargar equivalencias_canales.json ({e})")
        return {}


def canon(nombre):
    """Forma canónica para comparar nombres de canal de la web con las claves del JSON."""
    s = norm(nombre)
    s = re.sub(r"\s*-+>\s*\w+.*$", "", s)  # sufijos tipo "-> DAZN"
    return re.sub(r"\s+", " ", s).strip()


def indice_equivalencias(equivalencias):
    return {canon(k): k for k in equivalencias}


def canales_con_equivalencia(evento, indice):
    """Claves del JSON de equivalencias que corresponden a los canales del evento."""
    claves = []
    for canal in evento["canales"]:
        clave = indice.get(canon(canal))
        if clave and clave not in claves:
            claves.append(clave)
    return claves


# Calidad que puede acompañar al nombre de un canal en Elcano: "720p", "1080p", "*", "**", "HD"...
_CALIDAD_RE = re.compile(r"^(?:\d{3,4}p|(?:480|576|720|1080|2160)|\*+|u?hd|fhd|sd|4k)$")


def _tokens(nombre):
    s = norm(nombre).replace("+", "")
    s = re.sub(r"\*+", lambda m: f" {m.group()} ", s)
    return s.split()


def coincide_canal(titulo_elcano, subcanal):
    """
    True si el título de Elcano es el subcanal, con o sin calidad detrás.
    "M+ Deportes 2 720p *" coincide con "M+ Deportes 2"
    pero "M+ Deportes 2 720p *" NO coincide con "M+ Deportes".
    Se admite también que el subcanal lleve la calidad y el título no.
    """
    a, b = _tokens(titulo_elcano), _tokens(subcanal)
    if not a or not b:
        return False
    corto, largo = (a, b) if len(a) <= len(b) else (b, a)
    if largo[: len(corto)] != corto:
        return False
    return all(_CALIDAD_RE.match(t) for t in largo[len(corto):])


def build_events_m3u(agenda, equivalencias, elcano, path):
    """
    Solo se generan entradas para canales que figuran en el JSON de equivalencias.
    Los eventos sin ningún canal equivalente se descartan.
    """
    lines, vistos = [], set()
    hash_list = elcano.get("hashes", [])
    indice = indice_equivalencias(equivalencias)
    eventos_validos = 0

    for e in agenda:
        usado = False
        for web_channel in e["canales"]:
            clave = indice.get(canon(web_channel))
            if clave is None:
                continue  # canal fuera del JSON de equivalencias: se ignora

            subcanales = equivalencias[clave]
            if isinstance(subcanales, str):
                subcanales = [subcanales]
            subcanales = [s for s in (subcanales or []) if isinstance(s, str)] or [clave]

            for item in hash_list:
                h = (item.get("hash") or "").strip().lower()
                if not h:
                    continue
                titulo = item.get("title", "")
                coincidentes = [s for s in subcanales if coincide_canal(titulo, s)]
                if not coincidentes:
                    continue
                # Si coinciden varios, nos quedamos con el más específico (el más largo)
                nombre_canal = max(coincidentes, key=lambda s: len(_tokens(s)))

                k = (e["fecha"], e["hora"], e["partido"], nombre_canal, h)
                if k in vistos:
                    continue
                vistos.add(k)
                usado = True

                _, calidad, _ = split_title(titulo)
                name = f"{e['hora']} - {e['partido']} ({nombre_canal})"
                if calidad: name += f" ({calidad})"
                name += f" ({h[:3]})"
                group = f"{e['fecha']} | {e['competicion']}"
                lines.append(f'#EXTINF:-1 group-title="{attr(group)}" tvg-name="{attr(name)}",{name}')
                lines.append(EVENTS_URL_TEMPLATE.format(hash=h))
        if usado:
            eventos_validos += 1

    log(f"Eventos con canal en equivalencias y enlace en Elcano: {eventos_validos}/{len(agenda)}")
    if lines: write_m3u(path, lines)
    return len(lines) // 2


# --- Hilo Principal ---
def main():
    errores = []

    # 1. Elcano
    elcano, elcano_cid = None, None
    try:
        elcano, _, elcano_cid = fetch_elcano()
        write_json(ELCANO_FILE, elcano)
        n = build_channels_m3u(elcano, CHANNELS_M3U)
        log(f"Guardado {ELCANO_FILE} y {CHANNELS_M3U} ({n} canales)")
    except Exception as e:
        log(f"ERROR con Elcano: {e}")
        try:
            with open(ELCANO_FILE, "rb") as f: elcano = _validate_elcano(f.read())
            log(f"AVISO: se usa la copia anterior de {ELCANO_FILE}")
        except Exception:
            elcano = None
            errores.append("elcano")

    # 2. Equivalencias y Agenda
    if elcano:
        equivalencias = fetch_equivalencias()
        log(f"Equivalencias cargadas: {len(equivalencias)} claves")
        if not equivalencias:
            log("ERROR: sin equivalencias no se puede filtrar; no se toca el m3u de eventos")
            errores.append("equivalencias")
        else:
            try:
                agenda = scrape_futbolenlatv()
                log(f"Agenda descargada: {len(agenda)} eventos encontrados en futbolenlatv.es")
                indice = indice_equivalencias(equivalencias)
                for e in agenda:
                    e["canales_equivalencia"] = canales_con_equivalencia(e, indice)
                n = build_events_m3u(agenda, equivalencias, elcano, EVENTS_M3U)
                log(f"Guardado {EVENTS_M3U}: {n} entradas generadas")

                resultado = {
                    "fuente": "futbolenlatv.es/deporte",
                    "elcano_cid": elcano_cid,
                    "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "agenda": agenda,
                }
                if agenda:
                    write_json(OUTPUT_FILE, resultado)
                    log(f"Guardado {OUTPUT_FILE}")
                else:
                    log(f"AVISO: agenda vacía; no se sobrescribe {OUTPUT_FILE}")
                    errores.append("eventos")
            except Exception as e:
                log(f"ERROR construyendo agenda de eventos: {e}")
                errores.append("eventos")
    else:
        log("Sin datos de Elcano no se cruzan eventos.")

    if errores: sys.exit(1)


if __name__ == "__main__":
    main()
