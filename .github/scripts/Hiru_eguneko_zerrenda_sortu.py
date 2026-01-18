
# -*- coding: utf-8 -*-
import os
import re
import sys
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse, urljoin

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
    "User-Agent": "Mozilla/5.0 (compatible; M3U-Bot/1.4; +https://github.com/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Cabeceras del M3U solicitadas
M3U_HEADER_1 = '#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/EPG_dobleM.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"'
M3U_HEADER_2 = "#EXTVLCOPT:network-caching=1000"

ACE_HTTP_PREFIX = "http://127.0.0.1:6878/ace/getstream?id="

# Regex
HEX40_RE = re.compile(r"\b[a-fA-F0-9]{40}\b")
ACE_URL_RE = re.compile(r"acestream://([a-fA-F0-9]{40})", re.IGNORECASE)
DATE_TOKEN_RE = re.compile(r"\b(\d{2})/-\b")
STREAM_LINKS_CLASS_RE = re.compile(r"\bstream[-_\s]*links\b", re.IGNORECASE)


def log(msg: str):
    print(f"[m3u] {msg}", flush=True)


def build_url_for_gateway(base_gateway: str, original_url: str) -> str:
    u = urlparse(original_url)
    path, qs = u.path, u.query
    gateway = base_gateway.rstrip("/")
    return f"{gateway}{path}" + (f"?{qs}" if qs else "")


def iter_candidate_urls():
    for gw in IPFS_GATEWAYS:
        yield build_url_for_gateway(gw, TARGET_URL), gw


def _debug_dump(html: str, suffix: str):
    if not DEBUG:
        return
    dbg_dir = Path(".debug")
    dbg_dir.mkdir(parents=True, exist_ok=True)
    (dbg_dir / f"debug_source_{suffix}.html").write_text(html, encoding="utf-8", errors="ignore")


def fetch_html() -> Tuple[str, str]:
    """
    Descarga el HTML y devuelve (html, gateway_usado).
    Si USE_LOCAL_HTML está definido, devuelve (html_local, 'local').
    """
    if USE_LOCAL_HTML:
        p = Path(USE_LOCAL_HTML)
        if not p.exists():
            log(f"Fichero local no encontrado: {p}")
            sys.exit(1)
        log(f"Usando HTML local: {p}")
        text = p.read_text(encoding="utf-8", errors="ignore")
        _debug_dump(text, suffix="local")
        return text, "local"

    if not TARGET_URL:
        log("TARGET_URL vacío")
        sys.exit(1)

    proxies_candidates = [None] + PROXY_LIST if PROXY_LIST else [None]

    for url, gateway in iter_candidate_urls():
        for proxy in proxies_candidates:
            try:
                proxies = {"http": proxy, "https": proxy} if proxy else None
                log(f"GET {url}" + (f" vía proxy {proxy}" if proxy else " sin proxy"))
                resp = requests.get(url, headers=HEADERS, timeout=25, proxies=proxies)
                if resp.status_code == 200 and resp.text:
                    log(f"OK {url}")
                    _debug_dump(resp.text, suffix="fetched")
                    return resp.text, gateway
                else:
                    log(f"Fallo {url}: HTTP {resp.status_code}")
            except Exception as ex:
                log(f"Error {url} (proxy={proxy}): {ex}")

    log("No fue posible descargar la página desde ningún gateway/proxy.")
    sys.exit(2)


def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def extract_near_date_str(node) -> str:
    # 1) Ancestros
    for anc in node.parents:
        try:
            txt = normalize_space(anc.get_text(" ", strip=True))
        except Exception:
            txt = ""
        m = DATE_TOKEN_RE.search(txt)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        for attr in ("data-date", "date", "data-fecha"):
            v = anc.get(attr)
            if v:
                m = DATE_TOKEN_RE.search(str(v))
                if m:
                    return f"{m.group(1)}-{m.group(2)}"
    # 2) Hermanos anteriores
    sib = node
    for _ in range(20):
        sib = sib.previous_sibling
        if sib is None:
            break
        if getattr(sib, "get_text", None):
            txt = normalize_space(sib.get_text(" ", strip=True))
            m = DATE_TOKEN_RE.search(txt)
            if m:
                return f"{m.group(1)}-{m.group(2)}"
    # 3) Fallback
    return datetime.utcnow().strftime("%d-%m")


def extract_competition(node) -> str:
    comp = node.select_one("span.competition-name")
    if comp and comp.get_text(strip=True):
        return normalize_space(comp.get_text(strip=True))
    for anc in node.parents:
        comp = getattr(anc, "select_one", lambda *_: None)("span.competition-name")
        if comp and comp.get_text(strip=True):
            return normalize_space(comp.get_text(strip=True))
    return ""


def _iter_attrs(tag) -> Iterable[str]:
    for _, v in (tag.attrs or {}).items():
        if isinstance(v, (list, tuple)):
            for x in v:
                yield str(x)
        else:
            yield str(v)


def extract_ace_ids_from_stream_container(container) -> List[str]:
    ids = set()
    frag = str(container)
    for m in ACE_URL_RE.findall(frag):
        ids.add(m.lower())
    for m in HEX40_RE.findall(frag):
        ids.add(m.lower())
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


def find_stream_container_inside_event(event_node):
    for el in event_node.find_all(True):
        classes = el.get("class", [])
        if any(STREAM_LINKS_CLASS_RE.search(cls) for cls in classes):
            return el
    return None


def _collect_toggle_targets(event_node) -> List[str]:
    targets = set()
    for el in event_node.find_all(True):
        for attr in ("data-bs-target", "data-target", "aria-controls", "href"):
            v = el.get(attr)
            if not v:
                continue
            m = re.search(r"#([A-Za-z0-9_\-:]+)", v)
            if m:
                targets.add(m.group(1))
            else:
                if re.match(r"^[A-Za-z0-9_\-:]+$", v):
                    targets.add(v)
    return list(targets)


def find_panel_by_targets(soup: BeautifulSoup, targets: List[str]):
    for tid in targets:
        panel = soup.find(id=tid)
        if panel:
            if any(STREAM_LINKS_CLASS_RE.search(c) for c in panel.get("class", [])):
                return panel
            inside = panel.find(class_=STREAM_LINKS_CLASS_RE)
            if inside:
                return inside
    return None


def _collect_remote_panel_urls(event_node) -> List[str]:
    urls = set()
    for el in event_node.find_all(True):
        for attr in ("data-url", "data-src", "data-href", "href"):
            v = el.get(attr)
            if not v:
                continue
            if v.strip().startswith("#"):
                continue
            urls.add(v.strip())
    return list(urls)


def _rewrite_to_gateway(url_like: str, gateway_used: str) -> str:
    base = build_url_for_gateway(gateway_used, TARGET_URL)
    u = urlparse(url_like)
    if not u.scheme:
        return urljoin(base, url_like)
    if "ipfs.io" in u.netloc:
        new_u = u._replace(netloc=urlparse(gateway_used).netloc)
        return urlunparse(new_u)
    return url_like


def fetch_remote_panel(url_like: str, gateway_used: str) -> Optional[str]:
    url = _rewrite_to_gateway(url_like, gateway_used)
    proxies_candidates = [None] + PROXY_LIST if PROXY_LIST else [None]
    for proxy in proxies_candidates:
        try:
            proxies = {"http": proxy, "https": proxy} if proxy else None
            log(f"GET panel {url}" + (f" vía proxy {proxy}" if proxy else " sin proxy"))
            resp = requests.get(url, headers=HEADERS, timeout=20, proxies=proxies)
            if resp.status_code == 200 and resp.text:
                if DEBUG:
                    _debug_dump(resp.text, suffix=f"panel_{hashlib.md5(url.encode()).hexdigest()[:8]}")
                return resp.text
            else:
                log(f"Panel fallo {url}: HTTP {resp.status_code}")
        except Exception as ex:
            log(f"Panel error {url} (proxy={proxy}): {ex}")
    return None


def find_associated_stream_container(soup: BeautifulSoup, event_node, gateway_used: str):
    # 1) Dentro del propio evento
    container = find_stream_container_inside_event(event_node)
    if container:
        return container
    # 2) Panel colapsable referenciado
    targets = _collect_toggle_targets(event_node)
    panel = find_panel_by_targets(soup, targets)
    if panel:
        return panel
    # 3) Panel remoto (AJAX)
    remote_urls = _collect_remote_panel_urls(event_node)
    for ru in remote_urls:
        html = fetch_remote_panel(ru, gateway_used)
        if not html:
            continue
        frag = BeautifulSoup(html, "lxml")
        inside = frag.find(class_=STREAM_LINKS_CLASS_RE)
        if inside:
            return inside
    # 4) Hermanos siguientes hasta el próximo evento
    sib = event_node
    for _ in range(30):
        sib = sib.find_next_sibling()
        if sib is None:
            break
        if sib.get("data-event-id"):
            break
        inside = sib.find(class_=STREAM_LINKS_CLASS_RE)
        if inside:
            return inside
    return None


def build_m3u_entry(group_title: str, name: str, ace_id: str, include_suffix: bool) -> str:
    display_name = name
    if include_suffix and ace_id:
        display_name = f"{display_name} ({ace_id[:3]})"
    line1 = f'#EXTINF:-1 group-title="{group_title}" tvg-name="{display_name}",{display_name}'
    line2 = f"{ACE_HTTP_PREFIX}{ace_id}"
    return f"{line1}\n{line2}"


def write_if_changed(content: str, path_out: Path, history_dir: Path, keep_last: int = 50):
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

    def _hash(b): return hashlib.sha256(b).hexdigest()
    new_hash = _hash(new_bytes)

    history_files = sorted(history_dir.glob("zz_eventos_ott_*.m3u"), key=lambda p: p.stat().st_mtime, reverse=True)
    latest_hash = _hash(history_files[0].read_bytes()) if history_files else None

    if latest_hash != new_hash:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        hist_path = history_dir / f"zz_eventos_ott_{ts}.m3u"
        hist_path.write_bytes(new_bytes)
        log(f"Guardado histórico: {hist_path.name}")

    history_files = sorted(history_dir.glob("zz_eventos_ott_*.m3u"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in history_files[keep_last:]:
        try:
            old.unlink(missing_ok=True)
        except Exception:
            pass


def main():
    html, gateway_used = fetch_html()
    if DEBUG:
        log(f"HTML recibido: {len(html)} bytes (gateway: {gateway_used})")

    soup = BeautifulSoup(html, "lxml")

    # Buscar nodos de evento (flexible)
    events = soup.select("tr.event-detail, [data-event-id]")
    events = [n for n in events if n.get("data-event-id")]
    log(f"Eventos detectados: {len(events)}")

    if DEBUG:
        dbg_dir = Path(".debug"); dbg_dir.mkdir(parents=True, exist_ok=True)
        (dbg_dir / "debug_found_events.txt").write_text(
            "\n".join([(n.get("data-event-id") or "").strip() for n in events]),
            encoding="utf-8"
        )

    entries: List[str] = []

    for event_node in events:
        event_id = (event_node.get("data-event-id") or "").strip()
        if not event_id:
            continue

        comp = extract_competition(event_node)
        date_str = extract_near_date_str(event_node)
        group_title = normalize_space(f"{date_str} {comp}".strip())

        container = find_associated_stream_container(soup, event_node, gateway_used)
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

    write_if_changed(m3u_text, Path(OUTPUT_FILE), Path(HISTORY_DIR), keep_last=50)


if __name__ == "__main__":
    main()
