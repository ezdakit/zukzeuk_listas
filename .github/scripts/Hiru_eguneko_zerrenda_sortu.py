
# -*- coding: utf-8 -*-
import os
import re
import sys
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------
# Config desde variables de entorno
# ---------------------------
TARGET_URL = os.environ.get("TARGET_URL", "").strip()
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "zz_eventos_ott.m3u").strip()
HISTORY_DIR = os.environ.get("HISTORY_DIR", "history").strip()
PROXY_LIST = [p.strip() for p in os.environ.get("PROXY_LIST", "").split(",") if p.strip()]
USE_LOCAL_HTML = os.environ.get("USE_LOCAL_HTML", "").strip()
INCLUDE_ID_SUFFIX = os.environ.get("INCLUDE_ID_SUFFIX", "true").lower() == "true"
ALLOW_IPFS_IO = os.environ.get("ALLOW_IPFS_IO", "false").lower() == "true"

# Gateways alternativos a ipfs.io; se probarán en orden
IPFS_GATEWAYS = [
    "https://cloudflare-ipfs.com",
    "https://dweb.link",
    "https://cf-ipfs.com",
    "https://ipfs.runfission.com",
]
if ALLOW_IPFS_IO:
    IPFS_GATEWAYS.append("https://ipfs.io")  # como último recurso


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; M3U-Bot/1.0; +https://github.com/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Cabeceras del M3U solicitadas
M3U_HEADER_1 = '#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/EPG_dobleM.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"'
M3U_HEADER_2 = "#EXTVLCOPT:network-caching=1000"

ACE_HTTP_PREFIX = "http://127.0.0.1:6878/ace/getstream?id="

HEX40_RE = re.compile(r"\b[a-fA-F0-9]{40}\b")
ACE_URL_RE = re.compile(r"acestream://([a-fA-F0-9]{40})", re.IGNORECASE)
DATE_TOKEN_RE = re.compile(r"\b(\d{2})/-\b")  # DD-MM o DD/MM


def log(msg: str):
    print(f"[m3u] {msg}", flush=True)


def build_url_for_gateway(base_gateway: str, original_url: str) -> str:
    """
    Dado un gateway base (e.g. https://cloudflare-ipfs.com) y la URL original ipfs.io/ipns/...,
    remapea manteniendo /ipns/<id> y querystring (?tab=agenda).
    """
    # Extrae el path /ipns/... y la query
    # Ejemplo original_url:
    # https://ipfs.io/ipns/k2k4...004/?tab=agenda
    from urllib.parse import urlparse, urlunparse

    u = urlparse(original_url)
    path = u.path  # e.g., /ipns/<id>/
    qs = u.query   # e.g., tab=agenda

    # Asegura que base_gateway no lleva slash final duplicado
    gateway = base_gateway.rstrip("/")

    # Reconstruye
    new_url = f"{gateway}{path}"
    if qs:
        new_url = f"{new_url}?{qs}"
    return new_url


def iter_candidate_urls():
    for gw in IPFS_GATEWAYS:
        yield build_url_for_gateway(gw, TARGET_URL)


def fetch_html() -> str:
    """
    Descarga el HTML probando gateways y rotando proxies, o lee un fichero local si USE_LOCAL_HTML está definido.
    """
    if USE_LOCAL_HTML:
        p = Path(USE_LOCAL_HTML)
        if not p.exists():
            log(f"Fichero local no encontrado: {p}")
            sys.exit(1)
        log(f"Usando HTML local: {p}")
        return p.read_text(encoding="utf-8", errors="ignore")

    if not TARGET_URL:
        log("TARGET_URL vacío")
        sys.exit(1)

    candidates = list(iter_candidate_urls())
    if not candidates:
        log("No hay gateways configurados.")
        sys.exit(1)

    proxies_candidates = [None] + PROXY_LIST if PROXY_LIST else [None]

    for url in candidates:
        for proxy in proxies_candidates:
            try:
                if proxy:
                    proxies = {"http": proxy, "https": proxy}
                    log(f"GET {url} vía proxy {proxy}")
                else:
                    proxies = None
                    log(f"GET {url} sin proxy")

                resp = requests.get(url, headers=HEADERS, timeout=20, proxies=proxies)
                if resp.status_code == 200 and resp.text:
                    log(f"OK {url}")
                    return resp.text
                else:
                    log(f"Fallo {url}: HTTP {resp.status_code}")
            except Exception as ex:
                log(f"Error {url} (proxy={proxy}): {ex}")

    log("No fue posible descargar la página desde ningún gateway/proxy.")
    sys.exit(2)


def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def extract_near_date_str(node) -> str:
    """
    Intenta localizar una fecha (DD-MM o DD/MM) alrededor del evento, buscando en ancestros
    y hermanos anteriores algún texto que contenga un token de fecha.
    Fallback: fecha actual en Europe/Madrid.
    """
    # 1) Busca en ancestros con clases que sugieran fecha
    for anc in node.parents:
        txt = normalize_space(anc.get_text(" ", strip=True))
        m = DATE_TOKEN_RE.search(txt)
        if m:
            dd, mm = m.group(1), m.group(2)
            return f"{dd}-{mm}"

        # A veces hay atributos útiles
        for attr in ("data-date", "date", "data-fecha"):
            v = anc.get(attr)
            if v:
                m = DATE_TOKEN_RE.search(str(v))
                if m:
                    dd, mm = m.group(1), m.group(2)
                    return f"{dd}-{mm}"

    # 2) Busca en hermanos anteriores
    sib = node
    for _ in range(20):
        sib = sib.previous_sibling
        if sib is None:
            break
        if getattr(sib, "get_text", None):
            txt = normalize_space(sib.get_text(" ", strip=True))
            m = DATE_TOKEN_RE.search(txt)
            if m:
                dd, mm = m.group(1), m.group(2)
                return f"{dd}-{mm}"

    # 3) Fallback: fecha actual en Madrid
    try:
        from datetime import timezone, timedelta
        # Europe/Madrid → CET/CEST; para evitar dependencias, usamos UTC+1 aprox.
        # Si quieres exacto con DST, podemos añadir zoneinfo si está disponible.
        now_utc = datetime.utcnow()
        now = now_utc  # simplificamos; el día DD-MM suele ser el mismo
        return now.strftime("%d-%m")
    except Exception:
        return datetime.utcnow().strftime("%d-%m")


def extract_competition(node) -> str:
    # 1) en el propio nodo
    comp = node.select_one("span.competition-name")
    if comp and comp.get_text(strip=True):
        return normalize_space(comp.get_text(strip=True))
    # 2) en ancestros cercanos
    for anc in node.parents:
        comp = getattr(anc, "select_one", lambda *_: None)("span.competition-name")
        if comp and comp.get_text(strip=True):
            return normalize_space(comp.get_text(strip=True))
    return ""


def extract_acestream_ids_from_block(block_html: str):
    """Extrae IDs de acestream desde el HTML de un bloque (evento y filas siguientes)."""
    ids = set()
    # 1) acestream://<id>
    for m in ACE_URL_RE.findall(block_html):
        ids.add(m.lower())
    # 2) 40 hex sueltos
    for m in HEX40_RE.findall(block_html):
        ids.add(m.lower())
    return sorted(ids)


def collect_block_html_until_next_event(tr_node):
    """
    Devuelve el HTML del propio tr.event-detail y las filas siguientes
    hasta la próxima fila con class="event-detail" o fin de tabla.
    """
    html_parts = [str(tr_node)]
    sib = tr_node
    for _ in range(2000):  # límite de seguridad
        sib = sib.find_next_sibling()
        if sib is None:
            break
        classes = " ".join(sib.get("class", []))
        if "event-detail" in classes:
            break
        html_parts.append(str(sib))
    return "\n".join(html_parts)


def build_m3u_entry(group_title: str, name: str, ace_id: str, include_suffix: bool) -> str:
    """
    Construye la entrada M3U para el par evento–canal (acestream).
    - group-title: "DD-MM COMPETICIÓN"
    - tvg-name y nombre del canal: data-event-id [+ ' (' + primeros 3 chars + ')'] (si include_suffix)
    """
    display_name = name
    if include_suffix and ace_id:
        display_name = f"{display_name} ({ace_id[:3]})"

    line1 = f'#EXTINF:-1 group-title="{group_title}" tvg-name="{display_name}",{display_name}'
    line2 = f"{ACE_HTTP_PREFIX}{ace_id}"
    return f"{line1}\n{line2}"


def write_if_changed(content: str, path_out: Path, history_dir: Path, keep_last: int = 50):
    """
    Escribe el fichero principal y, si el contenido es distinto del último guardado en history,
    añade una nueva versión a history/ y elimina versiones antiguas manteniendo 'keep_last'.
    Política:
      - Siempre actualiza OUTPUT_FILE.
      - Añade a history/ sólo si el contenido es distinto al más reciente en history/
        (o si no hay histórico previo).
    """
    path_out.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    # Escribe/actualiza el output actual
    new_bytes = content.encode("utf-8")
    existing = path_out.read_bytes() if path_out.exists() else b""
    if existing != new_bytes:
        path_out.write_bytes(new_bytes)
        changed = True
    else:
        changed = False

    # Compara con el último en history
    history_files = sorted(history_dir.glob("zz_eventos_ott_*.m3u"), key=lambda p: p.stat().st_mtime, reverse=True)
    def _hash(b): return hashlib.sha256(b).hexdigest()

    new_hash = _hash(new_bytes)

    latest_hash = None
    if history_files:
        latest_bytes = history_files[0].read_bytes()
        latest_hash = _hash(latest_bytes)

    if latest_hash != new_hash:
        # Guarda una nueva versión en history
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        hist_path = history_dir / f"zz_eventos_ott_{ts}.m3u"
        hist_path.write_bytes(new_bytes)
        log(f"Guardado histórico: {hist_path.name}")

    # Limita a keep_last
    history_files = sorted(history_dir.glob("zz_eventos_ott_*.m3u"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in history_files[keep_last:]:
        try:
            old.unlink(missing_ok=True)
        except Exception:
            pass

    if changed:
        log(f"Actualizado {path_out}")
    else:
        log("Sin cambios en el fichero principal.")


def main():
    html = fetch_html()
    soup = BeautifulSoup(html, "lxml")

    entries = []

    # Encuentra filas de evento
    rows = soup.select("tr.event-detail")
    log(f"Eventos encontrados: {len(rows)}")

    for tr in rows:
        event_id = (tr.get("data-event-id") or "").strip()
        if not event_id:
            continue

        # Competición
        comp = extract_competition(tr)
        # Fecha (DD-MM)
        date_str = extract_near_date_str(tr)

        # Grupo
        group_title = normalize_space(f"{date_str} {comp}".strip())

        # Bloque HTML del evento + filas siguientes hasta próximo evento
        block_html = collect_block_html_until_next_event(tr)
        ace_ids = extract_acestream_ids_from_block(block_html)

        # Filtramos sólo si hay acestream_id
        for ace_id in ace_ids:
            entry = build_m3u_entry(group_title, event_id, ace_id, INCLUDE_ID_SUFFIX)
            entries.append(entry)

    # Construir M3U final
    m3u_lines = [M3U_HEADER_1, M3U_HEADER_2, ""]
    m3u_lines.extend(entries)
    m3u_text = "\n".join(m3u_lines).strip() + "\n"

    # Escribir resultado + histórico
    write_if_changed(m3u_text, Path(OUTPUT_FILE), Path(HISTORY_DIR), keep_last=50)


if __name__ == "__main__":
    main()
