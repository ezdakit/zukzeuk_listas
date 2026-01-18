
# -*- coding: utf-8 -*-
import os
import re
import sys
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

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
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

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
    "User-Agent": "Mozilla/5.0 (compatible; M3U-Bot/1.3; +https://github.com/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Cabeceras del M3U solicitadas
M3U_HEADER_1 = '#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/EPG_dobleM.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"'
M3U_HEADER_2 = "#EXTVLCOPT:network-caching=1000"

ACE_HTTP_PREFIX = "http://127.0.0.1:6878/ace/getstream?id="

# Regex
HEX40_RE = re.compile(r"\b[a-fA-F0-9]{40}\b")
ACE_URL_RE = re.compile(r"acestream://([a-fA-F0-9]{40})", re.IGNORECASE)
DATE_TOKEN_RE = re.compile(r"\b(\d{2})/-\b")  # DD-MM o DD/MM
STREAM_LINKS_CLASS_RE = re.compile(r"\bstream[-_\s]*links\b", re.IGNORECASE)


def log(msg: str):
    print(f"[m3u] {msg}", flush=True)


def build_url_for_gateway(base_gateway: str, original_url: str) -> str:
    """Remapea https://ipfs.io/ipns/... a <gateway>/ipns/... conservando la query (?tab=agenda)."""
    from urllib.parse import urlparse

    u = urlparse(original_url)
    path = u.path  # /ipns/<id>/
    qs = u.query   # tab=agenda
    gateway = base_gateway.rstrip("/")
    return f"{gateway}{path}" + (f"?{qs}" if qs else "")


def iter_candidate_urls():
    for gw in IPFS_GATEWAYS:
        yield build_url_for_gateway(gw, TARGET_URL)


def fetch_html() -> str:
    """Descarga el HTML (gateways alternativos + proxies) o lee un fichero local si USE_LOCAL_HTML está definido."""
    if USE_LOCAL_HTML:
        p = Path(USE_LOCAL_HTML)
        if not p.exists():
            log(f"Fichero local no encontrado: {p}")
            sys.exit(1)
        log(f"Usando HTML local: {p}")
        text = p.read_text(encoding="utf-8", errors="ignore")
        _debug_dump(text, suffix="local")
        return text

    if not TARGET_URL:
        log("TARGET_URL vacío")
        sys.exit(1)

    candidates = list(iter_candidate_urls())
    proxies_candidates = [None] + PROXY_LIST if PROXY_LIST else [None]

    for url in candidates:
        for proxy in proxies_candidates:
            try:
                proxies = {"http": proxy, "https": proxy} if proxy else None
                log(f"GET {url}" + (f" vía proxy {proxy}" if proxy else " sin proxy"))
                resp = requests.get(url, headers=HEADERS, timeout=25, proxies=proxies)
                if resp.status_code == 200 and resp.text:
                    log(f"OK {url}")
                    _debug_dump(resp.text, suffix="fetched")
                    return resp.text
                else:
                    log(f"Fallo {url}: HTTP {resp.status_code}")
            except Exception as ex:
                log(f"Error {url} (proxy={proxy}): {ex}")

    log("No fue posible descargar la página desde ningún gateway/proxy.")
    sys.exit(2)


def _debug_dump(html: str, suffix: str):
    if not DEBUG:
        return
    dbg_dir = Path(".debug")
    dbg_dir.mkdir(parents=True, exist_ok=True)
    (dbg_dir / f"debug_source_{suffix}.html").write_text(html, encoding="utf-8", errors="ignore")


def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def extract_near_date_str(node) -> str:
    """Busca fecha (DD-MM o DD/MM) en ancestros o hermanos anteriores. Fallback: hoy (UTC)."""
    # 1) Ancestros
    for anc in node.parents:
        try:
            txt = normalize_space(anc.get_text(" ", strip=True))
        except Exception:
            txt = ""
        m = DATE_TOKEN_RE.search(txt)
        if m:
            dd, mm = m.group(1), m.group(2)
            return f"{dd}-{mm}"
        for attr in ("data-date", "date", "data-fecha"):
            v = anc.get(attr)
            if v:
                m = DATE_TOKEN_RE.search(str(v))
                if m:
                    dd, mm = m.group(1), m.group(2)
                    return f"{dd}-{mm}"

    # 2) Hermanos anteriores (limitado)
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

    # 3) Fallback
    return datetime.utcnow().strftime("%d-%m")


def extract_competition(node) -> str:
    # 1) En el propio nodo
    comp = node.select_one("span.competition-name")
    if comp and comp.get_text(strip=True):
        return normalize_space(comp.get_text(strip=True))
    # 2) En ancestros cercanos
    for anc in node.parents:
        comp = getattr(anc, "select_one", lambda *_: None)("span.competition-name")
        if comp and comp.get_text(strip=True):
            return normalize_space(comp.get_text(strip=True))
    return ""


def _iter_attrs(tag) -> Iterable[str]:
    """Itera valores de atributos como strings (para buscar IDs también en atributos)."""
    for _, v in (tag.attrs or {}).items():
        if isinstance(v, (list, tuple)):
            for x in v:
                yield str(x)
        else:
            yield str(v)


def extract_ace_ids_from_stream_container(container) -> List[str]:
    """Extrae IDs de acestream desde el contenedor de stream-links (texto y atributos)."""
    ids = set()

    frag = str(container)
    # 1) acestream://<id> en texto/HTML
    for m in ACE_URL_RE.findall(frag):
        ids.add(m.lower())
    # 2) 40 hex sueltos en texto/HTML
    for m in HEX40_RE.findall(frag):
        ids.add(m.lower())

    # 3) Atributos
    for tag in container.find_all(True):
        for val in _iter_attrs(tag):
            m = ACE_URL_RE.search(val)
            if m:
                ids.add(m.group(1).lower())
            else:
                m2 = HEX40_RE.search(val)
                if m2:
                    ids.add(m2.group(0).lower())

    return sorted(ids)


def find_stream_container_inside_event(event_node) -> Optional[BeautifulSoup]:
    """Busca un contenedor stream-links dentro del propio nodo de evento."""
    for el in event_node.find_all(True):
        classes = el.get("class", [])
        if any(STREAM_LINKS_CLASS_RE.search(cls) for cls in classes):
            return el
    return None


def _collect_toggle_targets(event_node) -> List[str]:
    """
    Recolecta posibles ID de panel colapsable referenciado por el evento.
    Busca atributos: data-bs-target, data-target, aria-controls, href="#id".
    Devuelve IDs sin '#'.
    """
    targets = set()
    # candidatos: botones, enlaces, etc.
    for el in event_node.find_all(True):
        for attr in ("data-bs-target", "data-target", "aria-controls", "href"):
            v = el.get(attr)
            if not v:
                continue
            # puede ser "#panel-123" o "panel-123"
            m = re.search(r"#([A-Za-z0-9_\-:]+)", v)
            if m:
                targets.add(m.group(1))
            else:
                # si parece un id directo sin '#'
                if re.match(r"^[A-Za-z0-9_\-:]+$", v):
                    targets.add(v)
    return list(targets)


def find_associated_stream_container(soup: BeautifulSoup, event_node) -> Optional[BeautifulSoup]:
    """
    Encuentra el contenedor stream-links correspondiente al evento:
      1) dentro del propio <tr>
      2) en el/los panel(es) colapsables referenciados por el evento (via data-bs-target/aria-controls/href)
      3) en hermanos siguientes hasta el próximo tr.event-detail (fila colapsable contigua)
    """
    # (1) Dentro del propio evento
    container = find_stream_container_inside_event(event_node)
    if container:
        return container

    # (2) Paneles colapsables referenciados
    for target_id in _collect_toggle_targets(event_node):
        panel = soup.find(id=target_id)
        if panel:
            # Si el propio panel tiene la clase, úsalo; si no, busca dentro
            if panel.get("class") and any(STREAM_LINKS_CLASS_RE.search(c) for c in panel.get("class", [])):
                return panel
            inner = None
            for el in panel.find_all(True):
                classes = el.get("class", [])
                if any(STREAM_LINKS_CLASS_RE.search(cls) for cls in classes):
                    inner = el
                    break
            if inner:
                return inner

    # (3) Hermanos siguientes hasta el siguiente evento
    sib = event_node
    for _ in range(30):  # límite de seguridad
        sib = sib.find_next_sibling()
        if sib is None:
            break
        if sib.get("data-event-id"):  # llegó el siguiente evento
            break
        # buscar contenedor en este hermano
        for el in sib.find_all(True):
            classes = el.get("class", [])
            if any(STREAM_LINKS_CLASS_RE.search(cls) for cls in classes):
                return el

    return None


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
    """
    path_out.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    new_bytes = content.encode("utf-8")
    existing = path_out.read_bytes() if path_out.exists() else b""
    changed = existing != new_bytes
    if changed:
        path_out.write_bytes(new_bytes)
        log(f"Actualizado {path_out}")
    else:
        log("Sin cambios en el fichero principal.")

    # Comparar con el último del histórico
    def _hash(b): return hashlib.sha256(b).hexdigest()
    new_hash = _hash(new_bytes)

    history_files = sorted(history_dir.glob("zz_eventos_ott_*.m3u"), key=lambda p: p.stat().st_mtime, reverse=True)
    latest_hash = _hash(history_files[0].read_bytes()) if history_files else None

    if latest_hash != new_hash:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        hist_path = history_dir / f"zz_eventos_ott_{ts}.m3u"
        hist_path.write_bytes(new_bytes)
        log(f"Guardado histórico: {hist_path.name}")

    # Limitar a 'keep_last'
    history_files = sorted(history_dir.glob("zz_eventos_ott_*.m3u"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in history_files[keep_last:]:
        try:
            old.unlink(missing_ok=True)
        except Exception:
            pass


def main():
    html = fetch_html()
    if DEBUG:
        log(f"HTML recibido: {len(html)} bytes (depuración activada)")

    soup = BeautifulSoup(html, "lxml")

    # Buscar nodos de evento (flexible)
    events = soup.select("tr.event-detail, [data-event-id]")
    events = [n for n in events if n.get("data-event-id")]
    log(f"Eventos detectados: {len(events)}")

    entries = []

    for event_node in events:
        event_id = (event_node.get("data-event-id") or "").strip()
        if not event_id:
            continue

        comp = extract_competition(event_node)
        date_str = extract_near_date_str(event_node)
        group_title = normalize_space(f"{date_str} {comp}".strip())

        # Buscar el contenedor asociado (dentro, paneles target u hermanos próximos)
        container = find_associated_stream_container(soup, event_node)
        if not container:
            if DEBUG:
                log(f"[DEBUG] Sin contenedor stream-links para evento: {event_id}")
            continue

        ace_ids = extract_ace_ids_from_stream_container(container)
        if DEBUG:
            log(f"[DEBUG] Evento '{event_id}' -> acestream_ids: {ace_ids}")

        if not ace_ids:
            continue

        for ace_id in ace_ids:
            entries.append(build_m3u_entry(group_title, event_id, ace_id, INCLUDE_ID_SUFFIX))

    # Construir M3U final
    m3u_lines = [M3U_HEADER_1, M3U_HEADER_2, ""]
    m3u_lines.extend(entries)
    m3u_text = "\n".join(m3u_lines).strip() + "\n"

    # Escribir resultado + histórico
    write_if_changed(m3u_text, Path(OUTPUT_FILE), Path(HISTORY_DIR), keep_last=50)


if __name__ == "__main__":
    main()
