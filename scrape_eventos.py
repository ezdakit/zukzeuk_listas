#!/usr/bin/env python3
"""
Genera las listas de Acestream a partir de Elcano (hashes.json) y de la agenda
de futbolenlatv.es.

Salidas (raíz del repositorio):
  elcano.json                  copia de hashes.json
  ezdakit.m3u                  todos los canales de Elcano
  eventos.json                 agenda parseada (con los canales que tienen equivalencia)
  ezdakit_eventos.m3u          eventos cruzados con Elcano (solo canales del JSON de equivalencias)
  equivalencias_canales.json   copia del JSON de equivalencias de canales
  scraper.log                  control de ejecuciones (más reciente arriba, últimos 7 días)

Variables de entorno útiles:
  LOG_LEVEL=DEBUG|INFO|WARN|ERROR   (por defecto DEBUG: trazas muy detalladas)
  ELCANO_IPNS_KEYS                  claves IPNS de hashes.json separadas por comas (1ª preferente, 2ª reserva)
  ELCANO_DIRECT_BASES               servidores HTTP directos; se prueba <base>/<clave>/hashes.json para cada clave
  ELCANO_FALLBACK_URL(S)            URLs directas adicionales de hashes.json
  EQUIVALENCIAS_URLS                URLs del JSON de equivalencias, por orden; si fallan todas se usa la copia del repo
  ELCANO_MAX_SECONDS                presupuesto total para obtener hashes.json (por defecto 300)
  IPFS_GATEWAYS                     pasarelas IPFS separadas por comas
  SAVE_HTML=1                       guarda siempre el HTML de futbolenlatv en DEBUG_DIR
"""
import contextlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
import unicodedata
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import bs4
import requests
from bs4 import BeautifulSoup

# ============================================================================
# Configuración
# ============================================================================
# --- Elcano / IPFS ---
# Claves IPNS de hashes.json, por orden de preferencia (la 2ª es la de reserva)
ELCANO_IPNS_KEYS = [
    k.strip()
    for k in os.getenv(
        "ELCANO_IPNS_KEYS",
        "k51qzi5uqu5dh5qej4b9wlcr5i6vhc7rcfkekhrxqek5c9lk6gdaiik820fecs,"
        "k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr",
    ).split(",")
    if k.strip()
]
ELCANO_FILE_PATH = os.getenv("ELCANO_FILE_PATH", "hashes.json")
IPFS_GATEWAYS = [
    g.strip().rstrip("/")
    for g in os.getenv("IPFS_GATEWAYS", "https://dweb.link,https://ipfs.io,https://w3s.link,https://gateway.pinata.cloud").split(",")
    if g.strip()
]
# Servidores HTTP directos: para cada clave IPNS se prueba <base>/<clave>/<fichero>
ELCANO_DIRECT_BASES = [
    b.strip().rstrip("/")
    for b in os.getenv("ELCANO_DIRECT_BASES", "https://tokyo.elcano-ipfs.workers.dev").split(",")
    if b.strip()
]
# URLs directas adicionales de hashes.json (se prueban tras las de la 1ª clave)
ELCANO_FALLBACK_URLS = list(dict.fromkeys(
    u.strip()
    for u in (os.getenv("ELCANO_FALLBACK_URLS", "") + "," + os.getenv("ELCANO_FALLBACK_URL", "")).split(",")
    if u.strip()
))
# Timeouts (segundos) y presupuesto total para obtener hashes.json
IPFS_RESOLVE_TIMEOUT = int(os.getenv("IPFS_RESOLVE_TIMEOUT", "30"))   # ipfs resolve /ipns/...
IPFS_CAT_TIMEOUT = int(os.getenv("IPFS_CAT_TIMEOUT", "30"))           # ipfs cat /ipfs/<cid>/...
GATEWAY_TIMEOUT = int(os.getenv("GATEWAY_TIMEOUT", "20"))             # cada pasarela HTTP
DIRECT_URL_TIMEOUT = int(os.getenv("DIRECT_URL_TIMEOUT", "20"))       # cada URL directa
ELCANO_MAX_SECONDS = int(os.getenv("ELCANO_MAX_SECONDS", "300"))      # tope global de la fase 1

# --- Ficheros ---
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "eventos.json")
ELCANO_FILE = os.getenv("ELCANO_FILE", "elcano.json")
CHANNELS_M3U = os.getenv("CHANNELS_M3U", "ezdakit.m3u")
EVENTS_M3U = os.getenv("EVENTS_M3U", "ezdakit_eventos.m3u")
EQUIVALENCIAS_FILE = os.getenv("EQUIVALENCIAS_FILE", "equivalencias_canales.json")
SCRAPER_LOG_FILE = os.getenv("SCRAPER_LOG_FILE", "scraper.log")        # control de ejecuciones
SCRAPER_LOG_DAYS = int(os.getenv("SCRAPER_LOG_DAYS", "7"))             # días que se conservan
DEBUG_DIR = os.getenv("DEBUG_DIR", "debug")
EVENTS_URL_TEMPLATE = "http://127.0.0.1:6878/ace/getstream?id={hash}"
CHANNELS_URL_TEMPLATE = "http://127.0.0.1:6878/ace/getstream?id={hash}"

# --- Orígenes de datos ---
FUTBOL_URL = os.getenv("FUTBOL_URL", "https://www.futbolenlatv.es/deporte")
EQUIVALENCIAS_URLS = [
    u.strip()
    for u in os.getenv(
        "EQUIVALENCIAS_URLS",
        "https://kiroideuno.pages.gay/equivalencias_canales.json,"
        "https://andrenalina.wasmer.app/equivalencias_canales.json",
    ).split(",")
    if u.strip()
]
EQUIVALENCIAS_TIMEOUT = int(os.getenv("EQUIVALENCIAS_TIMEOUT", "15"))
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

HASH_RE = re.compile(r"^[a-f0-9]{40}$", re.I)

# ============================================================================
# Trazas
# ============================================================================
T0 = time.monotonic()
LOG_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
LOG_LEVEL = LOG_LEVELS.get(os.getenv("LOG_LEVEL", "DEBUG").strip().upper(), 10)
IN_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"


def _escape_annotation(texto):
    return str(texto).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def log(msg, level="INFO"):
    """Traza con hora, segundos desde el inicio y nivel. WARN/ERROR crean anotaciones en Actions."""
    if LOG_LEVELS.get(level, 20) < LOG_LEVEL:
        return
    ahora = datetime.now().strftime("%H:%M:%S")
    print(f"[{ahora} +{time.monotonic() - T0:6.1f}s] {level:<5} {msg}", flush=True)
    if IN_ACTIONS and level in ("WARN", "ERROR"):
        tipo = "warning" if level == "WARN" else "error"
        print(f"::{tipo}::{_escape_annotation(msg)}", flush=True)


def log_excepcion(contexto=""):
    """Traceback completo, solo en nivel DEBUG."""
    if LOG_LEVEL <= LOG_LEVELS["DEBUG"]:
        tb = traceback.format_exc().rstrip()
        log(f"{contexto}\n{tb}" if contexto else tb, "DEBUG")


@contextlib.contextmanager
def fase(titulo):
    """Bloque de log plegable en Actions, con duración."""
    t = time.monotonic()
    if IN_ACTIONS:
        print(f"::group::{titulo}", flush=True)
    log(f"▶ {titulo}")
    try:
        yield
    finally:
        log(f"■ {titulo} · {time.monotonic() - t:.1f}s")
        if IN_ACTIONS:
            print("::endgroup::", flush=True)


def log_entorno():
    log(f"Python {platform.python_version()} · {platform.platform()}")
    log(f"requests {requests.__version__} · beautifulsoup4 {bs4.__version__}")
    log(f"Hora UTC {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} · Madrid {datetime.now(ZoneInfo('Europe/Madrid')):%Y-%m-%d %H:%M:%S}")
    log(f"LOG_LEVEL={os.getenv('LOG_LEVEL', 'DEBUG')} · directorio de trabajo: {os.getcwd()}")
    for i, k in enumerate(ELCANO_IPNS_KEYS, 1):
        log(f"Elcano: clave IPNS {i}/{len(ELCANO_IPNS_KEYS)}: {k[:14]}…{k[-6:]}")
    log(f"Elcano: fichero {ELCANO_FILE_PATH} · presupuesto total {ELCANO_MAX_SECONDS}s")
    log(f"Elcano: timeouts · resolve {IPFS_RESOLVE_TIMEOUT}s · cat {IPFS_CAT_TIMEOUT}s · URL directa {DIRECT_URL_TIMEOUT}s · pasarela {GATEWAY_TIMEOUT}s")
    log(f"Elcano: servidores directos (uno por clave): {', '.join(ELCANO_DIRECT_BASES) or '(ninguno)'}")
    log(f"Elcano: URLs directas adicionales: {', '.join(ELCANO_FALLBACK_URLS) or '(ninguna)'}")
    log(f"Elcano: pasarelas: {', '.join(IPFS_GATEWAYS) or '(ninguna)'}")
    log(f"Agenda: {FUTBOL_URL}")
    for i, u in enumerate(EQUIVALENCIAS_URLS, 1):
        log(f"Equivalencias: URL {i}/{len(EQUIVALENCIAS_URLS)}: {u}")
    log(f"Equivalencias: copia en el repositorio: {EQUIVALENCIAS_FILE}")
    log(f"Salidas: {ELCANO_FILE}, {CHANNELS_M3U}, {OUTPUT_FILE}, {EVENTS_M3U}, {EQUIVALENCIAS_FILE}")


# Datos que se vuelcan al final en scraper.log
CTRL = {"inicio_utc": datetime.now(timezone.utc), "hashes": {}, "equivalencias": {}, "eventos": {}}
_FALLOS_ELCANO = []

# ============================================================================
# Utilidades
# ============================================================================
def norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).strip().lower()


def attr(value):
    return re.sub(r"\s+", " ", str(value or "")).replace('"', "'").strip()


def write_m3u(path, lines):
    texto = "\r\n".join(list(M3U_HEADER) + lines) + "\r\n"
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            if f.read() == texto:
                log(f"{path}: contenido idéntico al anterior (sin cambios)", "DEBUG")
    except FileNotFoundError:
        log(f"{path}: no existía, se crea", "DEBUG")
    except Exception as e:  # noqa: BLE001
        log(f"{path}: no se pudo comparar con la versión anterior ({e})", "DEBUG")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(texto)
    log(f"{path}: escrito · {len(lines) // 2} entradas · {os.path.getsize(path)} bytes")


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _sin_claves(d, ignorar):
    return {k: v for k, v in d.items() if k not in ignorar} if isinstance(d, dict) else d


def write_json_if_changed(path, data, ignorar=()):
    """Escribe el JSON solo si el contenido cambia (ignorando claves como la marca de tiempo)."""
    try:
        with open(path, encoding="utf-8") as f:
            anterior = json.load(f)
        if _sin_claves(anterior, ignorar) == _sin_claves(data, ignorar):
            log(f"{path}: contenido idéntico (no se reescribe)")
            return False
        log(f"{path}: el contenido ha cambiado", "DEBUG")
    except FileNotFoundError:
        log(f"{path}: no existía, se crea", "DEBUG")
    except Exception as e:  # noqa: BLE001
        log(f"{path}: no se pudo comparar con la versión anterior ({type(e).__name__}: {e})", "DEBUG")
    write_json(path, data)
    log(f"{path}: escrito · {os.path.getsize(path)} bytes")
    return True


def http_get(url, timeout=30, intentos=3):
    """GET con reintentos y trazas de estado, tamaño y duración."""
    for n in range(1, intentos + 1):
        t = time.monotonic()
        try:
            log(f"GET {url} (intento {n}/{intentos}, timeout {timeout}s)", "DEBUG")
            r = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
            log(
                f"  -> HTTP {r.status_code} · {len(r.content)} bytes · {time.monotonic() - t:.2f}s · "
                f"{r.headers.get('Content-Type', '?')} · url final: {r.url}",
                "DEBUG",
            )
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            ultimo = n == intentos
            log(
                f"  ✘ intento {n}/{intentos} ({time.monotonic() - t:.2f}s): {type(e).__name__}: {e}",
                "WARN" if ultimo else "INFO",
            )
            if ultimo:
                raise
            time.sleep(2 * n)


def guardar_debug(nombre, contenido):
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        ruta = os.path.join(DEBUG_DIR, nombre)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        log(f"Guardado {ruta} para depuración ({len(contenido)} caracteres)")
    except Exception as e:  # noqa: BLE001
        log(f"No se pudo guardar {nombre} de depuración: {e}", "WARN")


# ============================================================================
# Calidad de los títulos de Elcano
# ============================================================================
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


# ============================================================================
# Descarga de Elcano (hashes.json): nodo IPFS -> URL directa -> pasarelas
# ============================================================================
def _validate_elcano(raw):
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("hashes"), list) or not data["hashes"]:
        raise ValueError("el JSON no contiene una lista 'hashes' con datos")
    total = len(data["hashes"])
    validos = sum(1 for it in data["hashes"] if isinstance(it, dict) and HASH_RE.match((it.get("hash") or "").strip()))
    log(f"  JSON válido: {total} entradas en 'hashes', {validos} con hash de 40 hex · {len(raw)} bytes", "DEBUG")
    if validos == 0:
        raise ValueError("ninguna entrada de 'hashes' tiene un hash válido")
    return data


_IPFS_CLI_DISPONIBLE = True
_IPFS_ESTADO_LOGUEADO = False


def ipns_path(key):
    return f"/ipns/{key}/{ELCANO_FILE_PATH}"


def _ipfs(args, timeout):
    timeout = max(5, int(timeout))
    cmd = ["ipfs", *args, f"--timeout={timeout}s"]
    t = time.monotonic()
    log(f"$ {' '.join(cmd)}", "DEBUG")
    r = subprocess.run(cmd, capture_output=True, timeout=timeout + 15)
    err = r.stderr.decode("utf-8", "replace").strip()
    log(
        f"  rc={r.returncode} · {len(r.stdout)} bytes · {time.monotonic() - t:.1f}s"
        + (f" · stderr: {err[:200]}" if err else ""),
        "DEBUG",
    )
    if r.returncode != 0:
        raise RuntimeError(err[:300] or f"'ipfs {args[0]}' terminó con código {r.returncode}")
    return r.stdout


def _log_estado_ipfs(ruta):
    """Versión y peers del nodo; solo se registra la primera vez."""
    global _IPFS_ESTADO_LOGUEADO
    if _IPFS_ESTADO_LOGUEADO:
        return
    _IPFS_ESTADO_LOGUEADO = True
    log(f"ipfs en {ruta} · IPFS_PATH={os.getenv('IPFS_PATH', '(no definido)')}", "DEBUG")
    try:
        v = subprocess.run(["ipfs", "--version"], capture_output=True, timeout=10)
        log(f"  {v.stdout.decode().strip() or v.stderr.decode().strip()}", "DEBUG")
        p = subprocess.run(["ipfs", "swarm", "peers"], capture_output=True, timeout=15)
        if p.returncode == 0:
            log(f"  peers conectados: {len([x for x in p.stdout.decode().splitlines() if x.strip()])}", "DEBUG")
        else:
            log(f"  'ipfs swarm peers' falló (¿demonio parado?): {p.stderr.decode('utf-8', 'replace').strip()[:150]}", "DEBUG")
    except Exception as e:  # noqa: BLE001
        log(f"  no se pudo consultar el estado del nodo: {type(e).__name__}: {e}", "DEBUG")


def _from_ipfs_cli(key, presupuesto):
    global _IPFS_CLI_DISPONIBLE
    ruta = shutil.which("ipfs")
    if not ruta:
        _IPFS_CLI_DISPONIBLE = False
        raise RuntimeError("el binario 'ipfs' no está instalado")
    _log_estado_ipfs(ruta)

    t = time.monotonic()
    resuelto = _ipfs(["resolve", f"/ipns/{key}"], min(IPFS_RESOLVE_TIMEOUT, presupuesto)).decode("utf-8").strip()
    m = re.search(r"/ipfs/([A-Za-z0-9]+)", resuelto)
    if not m:
        raise RuntimeError(f"respuesta inesperada de 'ipfs resolve': {resuelto[:120]!r}")
    cid = m.group(1)
    log(f"  IPNS resuelto a CID {cid}")
    restante = presupuesto - (time.monotonic() - t)
    return _ipfs(["cat", f"/ipfs/{cid}/{ELCANO_FILE_PATH}"], min(IPFS_CAT_TIMEOUT, restante)), cid


def _from_http(url, timeout=30):
    t = time.monotonic()
    timeout = max(5, timeout)
    log(f"GET {url} (timeout {timeout:.0f}s)", "DEBUG")
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        log(
            f"  -> HTTP {r.status} · {len(data)} bytes · {time.monotonic() - t:.2f}s · "
            f"{r.headers.get('Content-Type', '?')} · url final: {r.geturl()}",
            "DEBUG",
        )
        return data, None


def _fuentes_elcano():
    """
    Orden, para cada clave IPNS por orden de preferencia:
        nodo IPFS local -> URL(s) directa(s) de esa clave -> pasarelas IPFS
    Las URLs directas extra (ELCANO_FALLBACK_URL[S]) se prueban tras las de la 1ª clave.
    Cada fuente es (nombre, función(presupuesto_en_segundos), tipo).
    """
    fuentes, vistas = [], set()

    def directa(url):
        if url in vistas:
            return
        vistas.add(url)
        fuentes.append((f"URL directa {url}", lambda b, url=url: _from_http(url, min(DIRECT_URL_TIMEOUT, b)), "http"))

    for i, key in enumerate(ELCANO_IPNS_KEYS):
        etiqueta = f"clave {i + 1} ({key[:10]}…)"
        fuentes.append((f"nodo IPFS local · {etiqueta}", lambda b, key=key: _from_ipfs_cli(key, b), "cli"))
        for base in ELCANO_DIRECT_BASES:
            directa(f"{base}/{key}/{ELCANO_FILE_PATH}")
        if i == 0:
            for url in ELCANO_FALLBACK_URLS:
                directa(url)
        for gw in IPFS_GATEWAYS:
            fuentes.append((
                f"{gw} · {etiqueta}",
                lambda b, gw=gw, key=key: _from_http(f"{gw}{ipns_path(key)}", min(GATEWAY_TIMEOUT, b)),
                "http",
            ))
    return fuentes


def fetch_elcano():
    fuentes = _fuentes_elcano()
    log(f"Fuentes de hashes.json ({len(fuentes)}), en orden:")
    for i, (nombre, _, _) in enumerate(fuentes, 1):
        log(f"  {i:>2}. {nombre}")

    inicio = time.monotonic()
    rondas = 2
    for ronda in range(1, rondas + 1):
        for i, (nombre, obtener, tipo) in enumerate(fuentes, 1):
            restante = ELCANO_MAX_SECONDS - (time.monotonic() - inicio)
            if restante <= 5:
                raise RuntimeError(f"Presupuesto de {ELCANO_MAX_SECONDS}s agotado sin obtener hashes.json")
            if tipo == "cli" and not _IPFS_CLI_DISPONIBLE:
                log(f"Ronda {ronda}/{rondas} · fuente {i}/{len(fuentes)}: {nombre} -> omitida (ipfs no instalado)", "DEBUG")
                continue
            t = time.monotonic()
            log(f"Ronda {ronda}/{rondas} · fuente {i}/{len(fuentes)}: {nombre} · quedan {restante:.0f}s de presupuesto")
            try:
                raw, cid = obtener(restante)
                data = _validate_elcano(raw)
                log(f"✔ hashes.json obtenido de: {nombre} · {time.monotonic() - t:.1f}s · CID: {cid or 'n/d'}")
                return data, nombre, cid
            except Exception as e:  # noqa: BLE001
                log(f"  ✘ {nombre} (ronda {ronda}/{rondas}, {time.monotonic() - t:.1f}s): {type(e).__name__}: {e}")
                log_excepcion()
                _FALLOS_ELCANO.append(f"{nombre} ({type(e).__name__})")
        if ronda < rondas:
            if ELCANO_MAX_SECONDS - (time.monotonic() - inicio) <= 15:
                break
            log("Ninguna fuente respondió en esta ronda; se espera 5s y se repite", "WARN")
            time.sleep(5)
    raise RuntimeError("No se pudo obtener hashes.json de ninguna fuente")


def build_channels_m3u(elcano, path):
    lines, omitidos = [], 0
    for item in elcano["hashes"]:
        h = (item.get("hash") or "").strip().lower()
        if not h:
            omitidos += 1
            continue
        base, quality, stars = split_title(item.get("title"))
        name = f"{base.upper()} {stars} ({quality}) (E-{h[:3]})".replace("  ", " ").strip()
        tvg_id, group = attr(item.get("tvg_id", "Unknown")), attr(item.get("group", ""))
        lines.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{attr(name)}" group-title="{group}",{name}')
        lines.append(CHANNELS_URL_TEMPLATE.format(hash=h))
    if omitidos:
        log(f"{omitidos} entradas de Elcano sin hash omitidas en {path}", "WARN")
    if lines:
        write_m3u(path, lines)
    else:
        log(f"{path}: sin entradas; no se escribe", "WARN")
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
    descartes = Counter()

    tablas = soup.find_all("table")
    filas = soup.find_all("tr")
    log(f"HTML: {len(tablas)} tablas, {len(filas)} filas <tr> (fecha por defecto: {hoy})", "DEBUG")

    for tr in filas:
        celdas = tr.find_all(["td", "th"], recursive=False)
        if not celdas:
            descartes["fila sin celdas"] += 1
            continue

        # Fila de cabecera con la fecha
        es_cabecera = "cabeceraTabla" in (tr.get("class") or [])
        if es_cabecera or (len(celdas) == 1 and DATE_RE.search(_txt(celdas[0]))):
            m = DATE_RE.search(_txt(tr))
            if m:
                fecha_actual = m.group(1)
                log(f"Cabecera de tabla -> fecha {fecha_actual} ({_txt(tr)[:60]!r})", "DEBUG")
            else:
                log(f"Cabecera sin fecha reconocible: {_txt(tr)[:80]!r}", "WARN")
            continue

        if len(celdas) < 4:
            descartes[f"fila con {len(celdas)} celdas (<4)"] += 1
            continue

        m_hora = TIME_RE.search(_txt(celdas[0]))
        if not m_hora:
            descartes["sin hora válida"] += 1
            continue
        hora = m_hora.group(1)

        competicion = _txt(celdas[1])
        partes = [t for t in (_txt(c) for c in celdas[2:-1]) if t]
        canales = extraer_canales(celdas[-1])
        if not partes:
            descartes["sin texto de evento"] += 1
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

    if descartes:
        log("Filas descartadas: " + ", ".join(f"{k}: {v}" for k, v in descartes.items()), "DEBUG")
    return eventos


def scrape_futbolenlatv():
    r = http_get(FUTBOL_URL, timeout=30)
    log(f"Página descargada: {len(r.text)} caracteres · codificación {r.encoding}")
    if os.getenv("SAVE_HTML") == "1":
        guardar_debug("futbolenlatv.html", r.text)
    eventos = parse_agenda(r.text)

    por_fecha = Counter(e["fecha"] for e in eventos)
    log("Eventos por fecha: " + (", ".join(f"{f}: {n}" for f, n in por_fecha.items()) or "(ninguno)"))
    sin_canales = sum(1 for e in eventos if not e["canales"])
    if sin_canales:
        log(f"{sin_canales} eventos sin ningún canal", "DEBUG")
    if not eventos:
        guardar_debug("futbolenlatv.html", r.text)
        log("No se ha extraído ningún evento: ¿ha cambiado el HTML de la página?", "ERROR")
    elif len(por_fecha) < 2:
        log("Solo hay eventos de una fecha; ¿cambia el HTML de mañana/pasado?", "WARN")
    return eventos


# ============================================================================
# Equivalencias de canales  {canal de la web: [nombres de canal en Elcano]}
# ============================================================================
# Claves que pueden contener la fecha del JSON y claves que son metadatos (no canales)
CLAVES_FECHA = ("generated", "generado", "updated", "last_updated", "lastupdated", "fecha", "date", "timestamp")
CLAVES_META = set(CLAVES_FECHA) | {"version", "count", "total", "meta", "_meta", "$schema"}


def fecha_en_json(data):
    """Fecha/hora que figura en la cabecera del JSON, o None si no hay ninguna."""
    if isinstance(data, dict):
        for k, v in data.items():
            if str(k).lower() in CLAVES_FECHA and isinstance(v, (str, int, float)) and str(v).strip():
                return str(v)
    return None


def validar_equivalencias(data):
    if not isinstance(data, dict) or not data:
        raise ValueError("el JSON de equivalencias no es un diccionario con datos")
    limpio, vacias, meta = {}, [], []
    for clave, valor in data.items():
        if str(clave).lower() in CLAVES_META:
            meta.append(clave)
            continue
        if isinstance(valor, str):
            valor = [valor]
        if not isinstance(valor, list):
            meta.append(clave)  # un valor que no es lista no es un canal
            continue
        valor = [v for v in valor if isinstance(v, str) and v.strip()]
        if not valor:
            vacias.append(clave)
        limpio[clave] = valor
    if meta:
        log(f"Claves ignoradas por ser metadatos o tener formato inesperado: {meta[:10]}", "DEBUG")
    if not limpio:
        raise ValueError("el JSON de equivalencias no contiene canales con el formato esperado")
    subcanales = sum(len(v) for v in limpio.values())
    log(f"Equivalencias válidas: {len(limpio)} claves, {subcanales} subcanales", "DEBUG")
    if vacias:
        log(f"{len(vacias)} claves sin subcanales (se usará la propia clave): {vacias[:10]}", "DEBUG")
    return limpio


def _diff_equivalencias(anterior, nuevo):
    añadidas = [k for k in nuevo if k not in anterior]
    eliminadas = [k for k in anterior if k not in nuevo]
    cambiadas = [k for k in nuevo if k in anterior and anterior[k] != nuevo[k]]
    log(f"Cambios respecto a la copia guardada: +{len(añadidas)} claves, -{len(eliminadas)} claves, ~{len(cambiadas)} modificadas")
    for etiqueta, lista in (("añadidas", añadidas), ("eliminadas", eliminadas), ("modificadas", cambiadas)):
        if lista:
            log(f"  {etiqueta}: {lista[:15]}{' …' if len(lista) > 15 else ''}", "DEBUG")


def fetch_equivalencias():
    """Devuelve (equivalencias, origen). Orden: URL 1 -> URL 2 -> ... -> copia guardada en el repositorio."""
    c = CTRL["equivalencias"]
    fallos = []
    anterior = None
    try:
        with open(EQUIVALENCIAS_FILE, encoding="utf-8") as f:
            anterior = json.load(f)
        edad = (time.time() - os.path.getmtime(EQUIVALENCIAS_FILE)) / 3600
        log(f"Copia guardada: {EQUIVALENCIAS_FILE} · {os.path.getsize(EQUIVALENCIAS_FILE)} bytes · modificada hace {edad:.1f}h", "DEBUG")
    except FileNotFoundError:
        log(f"No hay copia guardada de {EQUIVALENCIAS_FILE}", "DEBUG")
    except Exception as e:  # noqa: BLE001
        log(f"La copia guardada de {EQUIVALENCIAS_FILE} no se puede leer: {type(e).__name__}: {e}", "WARN")

    for i, url in enumerate(EQUIVALENCIAS_URLS, 1):
        log(f"Equivalencias: fuente {i}/{len(EQUIVALENCIAS_URLS)}: {url}")
        try:
            r = http_get(url, timeout=EQUIVALENCIAS_TIMEOUT, intentos=2)
            crudo = r.json()
            data = validar_equivalencias(crudo)
        except Exception as e:  # noqa: BLE001
            log(f"  ✘ {url}: {type(e).__name__}: {e}")
            log_excepcion()
            fallos.append(f"{url} ({type(e).__name__})")
            continue

        log(f"✔ Equivalencias obtenidas de {url}")
        c.update(
            descargado=True, origen=url, fecha_json=fecha_en_json(crudo),
            last_modified=r.headers.get("Last-Modified"), claves=len(data),
            subcanales=sum(len(v) for v in data.values()), fallos=fallos,
        )
        try:
            if isinstance(anterior, dict):
                _diff_equivalencias(validar_equivalencias(anterior), data)
        except Exception:  # noqa: BLE001
            log("No se pudo comparar con la copia anterior (formato distinto)", "DEBUG")
        try:
            write_json_if_changed(EQUIVALENCIAS_FILE, crudo)  # se guarda tal cual lo sirve la web
        except Exception as e:  # noqa: BLE001
            log(f"No se pudo guardar {EQUIVALENCIAS_FILE}: {type(e).__name__}: {e}", "WARN")
        return data, f"web ({url})"

    log("No se pudieron obtener las equivalencias de ninguna URL", "WARN")
    if anterior is not None:
        try:
            data = validar_equivalencias(anterior)
            log(f"Se usa la última copia guardada en el repositorio: {EQUIVALENCIAS_FILE} ({len(data)} claves)", "WARN")
            c.update(
                descargado=False, origen=f"copia del repositorio ({EQUIVALENCIAS_FILE})",
                fecha_json=fecha_en_json(anterior), claves=len(data),
                subcanales=sum(len(v) for v in data.values()), fallos=fallos,
            )
            return data, "copia guardada en el repositorio"
        except Exception as e:  # noqa: BLE001
            log(f"La copia guardada tampoco es válida: {e}", "ERROR")
    c.update(descargado=False, origen="ninguno", error="sin URL disponible ni copia válida", fallos=fallos)
    return {}, "ninguna"


@lru_cache(maxsize=None)
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


@lru_cache(maxsize=None)
def _tokens(nombre):
    s = norm(nombre).replace("+", "")
    s = re.sub(r"\*+", lambda m: f" {m.group()} ", s)
    return tuple(s.split())


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


# ============================================================================
# Cruce eventos x equivalencias x Elcano
# ============================================================================
def cruzar_eventos(agenda, equivalencias, elcano):
    """
    Solo se generan entradas para canales que figuran en el JSON de equivalencias.
    Los eventos sin ningún canal equivalente se descartan.
    Devuelve (lineas_m3u, estadisticas).
    """
    indice = indice_equivalencias(equivalencias)

    streams, invalidos = [], 0
    for item in elcano.get("hashes", []):
        h = (item.get("hash") or "").strip().lower()
        if not HASH_RE.match(h):
            invalidos += 1
            continue
        streams.append((h, item.get("title", "")))
    if invalidos:
        log(f"{invalidos} entradas de Elcano sin hash válido (ignoradas en el cruce)", "WARN")
    log(f"Cruzando {len(agenda)} eventos · {len(streams)} streams de Elcano · {len(equivalencias)} claves de equivalencias")

    lines, vistos = [], set()
    sin_equiv = Counter()
    claves_vistas, claves_con_stream = set(), set()
    entradas_por_fecha = Counter()
    eventos_con_streams_por_fecha = Counter()
    eventos_con_equiv = eventos_con_entradas = 0

    for e in agenda:
        log(f"EVT {e['fecha']} {e['hora']} | {e['competicion']} | {e['partido']}", "DEBUG")
        log(f"    canales en la web ({len(e['canales'])}): {' | '.join(e['canales']) or '(ninguno)'}", "DEBUG")
        con_equiv = usado = False

        for web_channel in e["canales"]:
            clave = indice.get(canon(web_channel))
            if clave is None:
                sin_equiv[web_channel] += 1
                log(f"    ✘ {web_channel!r}: no está en el JSON de equivalencias", "DEBUG")
                continue

            con_equiv = True
            claves_vistas.add(clave)
            subcanales = equivalencias[clave] or [clave]
            log(f"    ✔ {web_channel!r} = clave {clave!r} · subcanales: {subcanales}", "DEBUG")

            encontrados = 0
            for h, titulo in streams:
                coincidentes = [s for s in subcanales if coincide_canal(titulo, s)]
                if not coincidentes:
                    continue
                # Si coinciden varios, nos quedamos con el más específico (el más largo)
                nombre_canal = max(coincidentes, key=lambda s: len(_tokens(s)))

                k = (e["fecha"], e["hora"], e["partido"], nombre_canal, h)
                if k in vistos:
                    log(f"        = duplicado omitido: {titulo!r} [{h[:3]}]", "DEBUG")
                    continue
                vistos.add(k)
                usado = True
                encontrados += 1
                claves_con_stream.add(clave)

                _, calidad, _ = split_title(titulo)
                name = f"{e['hora']} - {e['partido']} ({nombre_canal})"
                if calidad:
                    name += f" ({calidad})"
                name += f" ({h[:3]})"
                group = f"{e['fecha']} | {e['competicion']}"
                lines.append(f'#EXTINF:-1 group-title="{attr(group)}" tvg-name="{attr(name)}",{name}')
                lines.append(EVENTS_URL_TEMPLATE.format(hash=h))
                entradas_por_fecha[e["fecha"]] += 1
                log(f"        + {titulo!r} -> {nombre_canal!r} [{h[:3]}]", "DEBUG")

            if not encontrados:
                log(f"        ! ningún stream de Elcano para {clave!r}", "DEBUG")

        eventos_con_equiv += con_equiv
        eventos_con_entradas += usado
        if usado:
            eventos_con_streams_por_fecha[e["fecha"]] += 1
        if not con_equiv:
            log("    => descartado: ningún canal tiene equivalencia", "DEBUG")

    stats = {
        "eventos": len(agenda),
        "eventos_con_equivalencia": eventos_con_equiv,
        "eventos_con_entradas": eventos_con_entradas,
        "entradas": len(lines) // 2,
        "entradas_por_fecha": dict(entradas_por_fecha),
        "eventos_con_entradas_por_fecha": dict(eventos_con_streams_por_fecha),
        "canales_sin_equivalencia": sin_equiv,
        "claves_sin_stream": sorted(claves_vistas - claves_con_stream),
    }
    return lines, stats


def build_events_m3u(agenda, equivalencias, elcano, path):
    lines, stats = cruzar_eventos(agenda, equivalencias, elcano)
    log(
        f"Eventos: {stats['eventos']} · con canal en equivalencias: {stats['eventos_con_equivalencia']} · "
        f"con streams en Elcano: {stats['eventos_con_entradas']} · entradas m3u: {stats['entradas']}"
    )
    if stats["entradas_por_fecha"]:
        log("Entradas por fecha: " + ", ".join(f"{f}: {n}" for f, n in stats["entradas_por_fecha"].items()))
        log("Eventos con streams por fecha: " + ", ".join(f"{f}: {n}" for f, n in stats["eventos_con_entradas_por_fecha"].items()))
    if stats["claves_sin_stream"]:
        log(f"Claves de equivalencias sin ningún stream en Elcano hoy ({len(stats['claves_sin_stream'])}): {stats['claves_sin_stream']}", "WARN")
    top = stats["canales_sin_equivalencia"].most_common(15)
    if top:
        log("Canales de la web SIN equivalencia (los más frecuentes): " + "; ".join(f"{c} x{n}" for c, n in top))

    if lines:
        write_m3u(path, lines)
    else:
        log(f"{path}: 0 entradas generadas; se conserva el fichero anterior sin tocar", "WARN")
    return stats


# ============================================================================
# Resumen en la página de la ejecución de GitHub Actions
# ============================================================================
def escribir_resumen_actions(info):
    ruta = os.getenv("GITHUB_STEP_SUMMARY")
    if not ruta:
        return
    md = ["## Resumen de la ejecución", "", "| Dato | Valor |", "|---|---|"]
    for k, v in info.get("tabla", []):
        md.append(f"| {k} | {v} |")
    sin = info.get("sin_equivalencia") or []
    if sin:
        md += ["", "### Canales de la web sin equivalencia (top 15)", "", "| Canal | Eventos |", "|---|---|"]
        md += [f"| {c} | {n} |" for c, n in sin]
    huerf = info.get("claves_sin_stream") or []
    if huerf:
        md += ["", "### Claves de equivalencias sin stream en Elcano", ""] + [f"- {c}" for c in huerf]
    if info.get("errores"):
        md += ["", f"**Errores:** {', '.join(info['errores'])}"]
    try:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write("\n".join(md) + "\n")
    except Exception as e:  # noqa: BLE001
        log(f"No se pudo escribir el resumen de Actions: {e}", "DEBUG")


def log_ficheros_salida():
    for ruta in (ELCANO_FILE, CHANNELS_M3U, OUTPUT_FILE, EVENTS_M3U, EQUIVALENCIAS_FILE):
        if os.path.exists(ruta):
            edad = (time.time() - os.path.getmtime(ruta)) / 60
            log(f"  {ruta}: {os.path.getsize(ruta)} bytes · modificado hace {edad:.1f} min")
        else:
            log(f"  {ruta}: no existe", "WARN")


# ============================================================================
# scraper.log: control de ejecuciones (más reciente arriba, últimos N días)
# ============================================================================
SEP = "=" * 80
BLOQUE_RE = re.compile(r"(?m)^" + SEP + r"\nEJECUCIÓN (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC")


def _fmt_fuentes_fallidas(fallos):
    fallos = list(dict.fromkeys(f if len(f) <= 100 else f[:97] + "…" for f in (fallos or [])))
    if not fallos:
        return None
    mostrados = "; ".join(fallos[:6]) + (f"; … (+{len(fallos) - 6})" if len(fallos) > 6 else "")
    return f"{len(fallos)} → {mostrados}"


def _fmt_fichero_remoto(titulo, c, es_hashes):
    """Sección de hashes.json o de equivalencias_canales.json."""
    out = [titulo]
    if "descargado" not in c:
        out.append("  Estado:           no se llegó a ejecutar")
        return out
    if c["descargado"]:
        out.append("  Estado:           DESCARGADO")
    elif c.get("origen") == "ninguno":
        out.append("  Estado:           ERROR · no se pudo descargar y no hay copia en el repositorio")
    else:
        out.append("  Estado:           NO SE PUDO DESCARGAR · se usa la copia del repositorio")
    out.append(f"  Origen:           {c.get('origen', 'n/d')}")

    fecha = c.get("fecha_json")
    if c.get("origen") == "ninguno":
        pass  # no hay fichero del que leer la fecha
    elif fecha:
        out.append(f"  Fecha en el JSON: {fecha}")
    else:
        extra = f" (cabecera HTTP Last-Modified: {c['last_modified']})" if c.get("last_modified") else ""
        out.append(f"  Fecha en el JSON: el fichero no incluye fecha{extra}")

    if es_hashes:
        if c.get("entradas") is not None:
            cuenta = f" (campo 'count' del JSON: {c['count']})" if c.get("count") is not None else ""
            out.append(f"  Entradas:         {c['entradas']}{cuenta}")
    elif c.get("claves") is not None:
        out.append(f"  Canales (claves): {c['claves']} · subcanales: {c.get('subcanales', 0)}")

    fallidas = _fmt_fuentes_fallidas(c.get("fallos"))
    if fallidas:
        out.append(f"  Fuentes fallidas: {fallidas}")
    if c.get("error"):
        out.append(f"  Error:            {c['error']}")
    return out


def _clave_fecha(f):
    try:
        return datetime.strptime(f, "%d/%m/%Y")
    except ValueError:
        return datetime.max


def bloque_control(ctrl):
    ini = ctrl["inicio_utc"]
    madrid = ini.astimezone(ZoneInfo("Europe/Madrid"))
    L = [SEP, f"EJECUCIÓN {ini:%Y-%m-%d %H:%M:%S} UTC · {madrid:%Y-%m-%d %H:%M:%S} Madrid", SEP]

    L += _fmt_fichero_remoto("hashes.json", ctrl["hashes"], True)
    L.append("")
    L += _fmt_fichero_remoto("equivalencias_canales.json", ctrl["equivalencias"], False)
    L.append("")

    ev = ctrl["eventos"]
    L.append("eventos (futbolenlatv.es)")
    if "total" in ev:
        L.append(f"  Total extraídos:  {ev['total']}")
        for fecha in sorted(ev.get("por_dia", {}), key=_clave_fecha):
            L.append(f"    {fecha}: {ev['por_dia'][fecha]}")
        if "entradas_m3u" in ev:
            L.append(f"  ezdakit_eventos.m3u: {ev['entradas_m3u']} entradas · {ev.get('eventos_con_streams', 0)} eventos con streams")
            for fecha in sorted(ev.get("m3u_por_dia", {}), key=_clave_fecha):
                d = ev["m3u_por_dia"][fecha]
                L.append(f"    {fecha}: {d['entradas']} entradas · {d['eventos']} eventos")
    elif ev.get("error"):
        L.append(f"  Error:            {ev['error']}")
    elif ev.get("omitido"):
        L.append(f"  No ejecutado:     {ev['omitido']}")
    else:
        L.append("  no se llegó a ejecutar")
    L.append("")

    errores = ctrl.get("errores") or []
    estado = "OK" if not errores else "CON ERRORES (" + ", ".join(errores) + ")"
    L.append(f"Resultado: {estado} · duración {ctrl.get('duracion', 0):.1f}s")
    return "\n".join(L)


def actualizar_scraper_log(ctrl):
    """Añade el bloque de esta ejecución arriba del todo y descarta lo que supere SCRAPER_LOG_DAYS días."""
    nuevo = bloque_control(ctrl)
    try:
        with open(SCRAPER_LOG_FILE, encoding="utf-8") as f:
            texto = f.read()
    except FileNotFoundError:
        texto = ""
        log(f"{SCRAPER_LOG_FILE}: no existía, se crea", "DEBUG")

    marcas = list(BLOQUE_RE.finditer(texto))
    corte = ctrl["inicio_utc"] - timedelta(days=SCRAPER_LOG_DAYS)
    previos, descartados = [], 0
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if ts >= corte:
            previos.append(texto[m.start():fin].rstrip("\n"))
        else:
            descartados += 1

    with open(SCRAPER_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n\n".join([nuevo] + previos) + "\n")
    log(
        f"{SCRAPER_LOG_FILE}: {len(previos) + 1} ejecuciones conservadas "
        f"(últimos {SCRAPER_LOG_DAYS} días), {descartados} antiguas descartadas"
    )


# ============================================================================
# Hilo principal
# ============================================================================
def _cargar_copia_elcano():
    try:
        with open(ELCANO_FILE, "rb") as f:
            return _validate_elcano(f.read())
    except Exception as e:  # noqa: BLE001
        log(f"Tampoco hay copia anterior utilizable de {ELCANO_FILE}: {type(e).__name__}: {e}", "ERROR")
        return None


def ejecutar(errores):
    log_entorno()
    tabla = []

    # 1. Elcano
    elcano, elcano_cid, origen_elcano = None, None, "—"
    with fase("1/4 Elcano (hashes.json)"):
        try:
            elcano, origen_elcano, elcano_cid = fetch_elcano()
            CTRL["hashes"] = {
                "descargado": True,
                "origen": origen_elcano + (f" · CID {elcano_cid}" if elcano_cid else ""),
                "fecha_json": elcano.get("generated"),
                "entradas": len(elcano["hashes"]),
                "count": elcano.get("count"),
                "fallos": list(_FALLOS_ELCANO),
            }
        except Exception as e:  # noqa: BLE001
            log(f"ERROR con Elcano: {type(e).__name__}: {e}", "ERROR")
            log_excepcion()
            elcano = _cargar_copia_elcano()
            if elcano:
                origen_elcano = "copia anterior del repositorio"
                log(f"AVISO: se usa la copia anterior de {ELCANO_FILE}", "WARN")
                CTRL["hashes"] = {
                    "descargado": False,
                    "origen": f"copia del repositorio ({ELCANO_FILE})",
                    "fecha_json": elcano.get("generated"),
                    "entradas": len(elcano["hashes"]),
                    "count": elcano.get("count"),
                    "fallos": list(_FALLOS_ELCANO),
                }
            else:
                errores.append("elcano")
                CTRL["hashes"] = {
                    "descargado": False, "origen": "ninguno",
                    "error": "no se pudo descargar y no hay copia válida", "fallos": list(_FALLOS_ELCANO),
                }

        if elcano and CTRL["hashes"].get("descargado"):
            try:
                write_json_if_changed(ELCANO_FILE, elcano)
                n = build_channels_m3u(elcano, CHANNELS_M3U)
                log(f"{ELCANO_FILE} y {CHANNELS_M3U} actualizados ({n} canales)")
            except Exception as e:  # noqa: BLE001
                log(f"ERROR guardando los ficheros de Elcano: {type(e).__name__}: {e}", "ERROR")
                log_excepcion()
                errores.append("elcano")
    tabla.append(("Origen de hashes.json", origen_elcano))
    tabla.append(("Streams en Elcano", len(elcano["hashes"]) if elcano else 0))

    stats = None
    equivalencias, origen_eq = {}, "—"
    agenda = []

    if not elcano:
        log("Sin datos de Elcano no se cruzan eventos.", "ERROR")
        CTRL["eventos"] = {"omitido": "sin datos de Elcano"}
    else:
        # 2. Equivalencias
        with fase("2/4 Equivalencias de canales"):
            equivalencias, origen_eq = fetch_equivalencias()
            log(f"Equivalencias: {len(equivalencias)} claves · origen: {origen_eq}")
            if not equivalencias:
                log("Sin equivalencias no se puede filtrar; no se toca el m3u de eventos", "ERROR")
                errores.append("equivalencias")
        tabla.append(("Origen de equivalencias", f"{origen_eq} ({len(equivalencias)} claves)"))

        if not equivalencias:
            CTRL["eventos"] = {"omitido": "sin equivalencias de canales"}
        else:
            # 3. Agenda
            with fase("3/4 Agenda de futbolenlatv.es"):
                try:
                    agenda = scrape_futbolenlatv()
                    log(f"Agenda descargada: {len(agenda)} eventos")
                    CTRL["eventos"] = {
                        "total": len(agenda),
                        "por_dia": dict(Counter(e["fecha"] for e in agenda)),
                    }
                except Exception as e:  # noqa: BLE001
                    log(f"ERROR descargando la agenda: {type(e).__name__}: {e}", "ERROR")
                    log_excepcion()
                    CTRL["eventos"] = {"error": f"{type(e).__name__}: {e}"}
                    errores.append("eventos")
            tabla.append(("Eventos en la agenda", len(agenda)))

            # 4. Cruce y ficheros
            if agenda:
                with fase("4/4 Cruce y generación de ficheros"):
                    try:
                        indice = indice_equivalencias(equivalencias)
                        for e in agenda:
                            e["canales_equivalencia"] = canales_con_equivalencia(e, indice)
                        stats = build_events_m3u(agenda, equivalencias, elcano, EVENTS_M3U)
                        fechas = set(CTRL["eventos"].get("por_dia", {})) | set(stats["entradas_por_fecha"])
                        CTRL["eventos"].update(
                            entradas_m3u=stats["entradas"],
                            eventos_con_streams=stats["eventos_con_entradas"],
                            m3u_por_dia={
                                f: {
                                    "eventos": stats["eventos_con_entradas_por_fecha"].get(f, 0),
                                    "entradas": stats["entradas_por_fecha"].get(f, 0),
                                }
                                for f in fechas
                            },
                        )

                        resultado = {
                            "fuente": "futbolenlatv.es/deporte",
                            "elcano_cid": elcano_cid,
                            "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "agenda": agenda,
                        }
                        write_json_if_changed(OUTPUT_FILE, resultado, ignorar=("generado_utc",))
                    except Exception as e:  # noqa: BLE001
                        log(f"ERROR construyendo los ficheros de eventos: {type(e).__name__}: {e}", "ERROR")
                        log_excepcion()
                        errores.append("eventos")
            elif "eventos" not in errores:
                log(f"Agenda vacía: no se sobrescribe {OUTPUT_FILE} ni {EVENTS_M3U}", "ERROR")
                CTRL["eventos"] = {"total": 0, "por_dia": {}}
                errores.append("eventos")

    if stats:
        tabla += [
            ("Eventos con canal en equivalencias", stats["eventos_con_equivalencia"]),
            ("Eventos con streams en Elcano", stats["eventos_con_entradas"]),
            ("Entradas en ezdakit_eventos.m3u", stats["entradas"]),
        ]

    with fase("Resumen"):
        log_ficheros_salida()
        log(f"Duración total: {time.monotonic() - T0:.1f}s · errores: {errores or 'ninguno'}")
    escribir_resumen_actions({
        "tabla": tabla,
        "errores": errores,
        "sin_equivalencia": stats["canales_sin_equivalencia"].most_common(15) if stats else [],
        "claves_sin_stream": stats["claves_sin_stream"] if stats else [],
    })


def main():
    log("=== INICIO ===")
    CTRL["inicio_utc"] = datetime.now(timezone.utc)
    errores = []
    try:
        ejecutar(errores)
    except Exception as e:  # noqa: BLE001
        log(f"ERROR inesperado: {type(e).__name__}: {e}", "ERROR")
        log_excepcion()
        errores.append("inesperado")
    finally:
        # El control de ejecuciones se escribe siempre, incluso si algo ha fallado
        CTRL["errores"] = list(errores)
        CTRL["duracion"] = time.monotonic() - T0
        try:
            actualizar_scraper_log(CTRL)
        except Exception as e:  # noqa: BLE001
            log(f"No se pudo actualizar {SCRAPER_LOG_FILE}: {type(e).__name__}: {e}", "ERROR")
            log_excepcion()

    log("=== FIN ===" + (" (con errores)" if errores else ""), "ERROR" if errores else "INFO")
    if errores:
        sys.exit(1)


if __name__ == "__main__":
    main()
