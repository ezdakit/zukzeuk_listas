
# -*- coding: utf-8 -*-
import os
import re
import sys
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------
# Config desde variables de entorno
# ---------------------------
TARGET_URL = os.environ.get("TARGET_URL", "").strip()
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "zz_eventos_ott.m3u").strip()
HISTORY_DIR = os.environ.get("HISTORY_DIR", "history").strip()
PROXY_LIST = [p.strip() for p in os.environ.get("PROXY_LIST", "").split(",") if p.strip()]
INCLUDE_ID_SUFFIX = os.environ.get("INCLUDE_ID_SUFFIX", "true").lower() == "true"
ALLOW_IPFS_IO = os.environ.get("ALLOW_IPFS_IO", "false").lower() == "true"
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

def _get_int_env(name: str, default: int = 0) -> int:
    try:
        return int((os.environ.get(name, str(default)) or "").strip())
    except Exception:
        return default

# 0 => sin límite; >0 => procesa solo los N primeros eventos
MAX_EVENTS = _get_int_env("MAX_EVENTS", 0)

# Gateways alternativos a ipfs.io; se probarán en orden con Playwright
IPFS_GATEWAYS = [
    "https://cloudflare-ipfs.com",
    "https://dweb.link",
    "https://cf-ipfs.com",
    "https://ipfs.runfission.com",
]
if ALLOW_IPFS_IO:
    IPFS_GATEWAYS.append("https://ipfs.io")  # último recurso

# Cabeceras M3U
M3U_HEADER_1 = '#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/EPG_dobleM.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"'
M3U_HEADER_2 = "#EXTVLCOPT:network-caching=1000"
ACE_HTTP_PREFIX = "http://127.0.0.1:6878/ace/getstream?id="

# Regex
HEX40 = r"[a-fA-F0-9]{40}"
OPENACE_RE = re.compile(r"openAcestream\('\"['\"]\)")
DATE_TOKEN_RE = re.compile(r"\b(\d{2})/-\b")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36 M3U-Bot/1.6"

def log(msg: str): print(f"[m3u] {msg}", flush=True)

def build_url_for_gateway(base_gateway: str, original_url: str) -> str:
    u = urlparse(original_url)
    path, qs = u.path, u.query
    base = base_gateway.rstrip("/")
    return f"{base}{path}" + (f"?{qs}" if qs else "")

def _debug_write(name: str, content: str):
    if not DEBUG: return
    d = Path(".debug"); d.mkdir(parents=True, exist_ok=True)
    Path(d / name).write_text(content or "", encoding="utf-8", errors="ignore")

def normalize_space(s: str) -> str:
    import re as _re
    return _re.sub(r"\s+", " ", (s or "").strip())

def extract_near_date_str_from_html(fragment_html: str) -> str:
    try:
        soup = BeautifulSoup(fragment_html or "", "lxml")
        txt = normalize_space(soup.get_text(" ", strip=True))
        m = DATE_TOKEN_RE.search(txt)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
    except Exception:
        pass
    return datetime.utcnow().strftime("%d-%m")

def extract_competition_from_html(fragment_html: str) -> str:
    try:
        soup = BeautifulSoup(fragment_html or "", "lxml")
        comp = soup.select_one("span.competition-name")
        if comp and comp.get_text(strip=True):
            return normalize_space(comp.get_text(strip=True))
    except Exception:
        pass
    return ""

def parse_proxy_url_for_playwright(proxy_url: str) -> dict:
    u = urlparse(proxy_url)
    cfg = {"server": f"{u.scheme}://{u.hostname}:{u.port or 80}"}
    if u.username: cfg["username"] = u.username
    if u.password: cfg["password"] = u.password
    return cfg

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

    history_files = sorted(history_dir.glob("zz_eventos_ott_*.m3u"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
    latest_hash = _hash(history_files[0].read_bytes()) if history_files else None
    if latest_hash != new_hash:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        hist_path = history_dir / f"zz_eventos_ott_{ts}.m3u"
        hist_path.write_bytes(new_bytes)
        log(f"Guardado histórico: {hist_path.name}")

    history_files = sorted(history_dir.glob("zz_eventos_ott_*.m3u"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
    for old in history_files[keep_last:]:
        try: old.unlink(missing_ok=True)
        except Exception: pass

# --------- Utilidades estrictas de Agenda ---------

def ensure_agenda_tab(page) -> None:
    """
    Garantiza que estamos en la pestaña 'Agenda Deportiva' y que su contenedor está activo.
    """
    try:
        btn = page.locator('nav [data-tab="agendaTab"]')
        if btn.count() > 0:
            if "active" not in (btn.first.get_attribute("class") or ""):
                btn.first.click(timeout=2000)
        page.wait_for_selector("#agendaTab.tab-content.active", timeout=5000)
    except Exception:
        pass

def find_event_rows(page):
    """
    Selecciona SOLO las filas cabecera de evento dentro de la pestaña Agenda.
    """
    container = page.locator("#agendaTab")
    table = container.locator(".events-table")
    if table.count() == 0:
        return container.locator("tr.event-row[data-event-id]")
    return table.locator("tr.event-row[data-event-id]")

def expand_event_detail(page, event_row) -> None:
    """
    Intenta desplegar SOLO el detalle del evento clicando la fila cabecera.
    """
    try:
        event_row.click(timeout=2000)
    except Exception:
        toggles = event_row.locator("[data-bs-target], [data-target], [aria-controls], a[href^='#'], button[aria-controls]")
        for i in range(min(3, toggles.count())):
            try: toggles.nth(i).click(timeout=800)
            except Exception: pass

def get_stream_links_html_for_event(page, event_id: str) -> str | None:
    """
    Devuelve el HTML concatenado de TODOS los .stream-links
    dentro de la fila de detalle DEL MISMO evento:
      #agendaTab tr.event-detail[data-event-id='<event_id>'] .stream-links
    """
    try:
        page.wait_for_selector(f"#agendaTab tr.event-detail[data-event-id='{event_id}']", timeout=4000)
    except Exception:
        return None

    links = page.locator(f"#agendaTab tr.event-detail[data-event-id='{event_id}'] .stream-links")
    n = links.count()
    if n == 0:
        return None
    parts = []
    for i in range(n):
        parts.append(links.nth(i).inner_html())
    return "\n".join(parts) if parts else None

def extract_ids_from_stream_links_html(html: str) -> List[str]:
    """
    IDs exclusivamente desde onclick="openAcestream('<ID>')" de <a.stream-link>.
    """
    if not html: return []
    ids = set()
    for m in OPENACE_RE.findall(html):
        ids.add(m.lower())
    try:
        frag = BeautifulSoup(html, "lxml")
        for a in frag.select("a.stream-link[onclick]"):
            m = OPENACE_RE.search(a.get("onclick", ""))
            if m:
                ids.add(m.group(1).lower())
    except Exception:
        pass
    return sorted(ids)

# -----------------------------------------------

def main():
    if not TARGET_URL:
        log("TARGET_URL vacío"); sys.exit(1)

    entries: List[str] = []
    last_page_dump = ""

    with sync_playwright() as p:
        gateways = IPFS_GATEWAYS[:]
        proxies = [None] + PROXY_LIST if PROXY_LIST else [None]
        success = False

        for gw in gateways:
            url = build_url_for_gateway(gw, TARGET_URL)
            for proxy in proxies:
                browser = context = None
                try:
                    launch_kwargs = {"headless": True}
                    if proxy:
                        launch_kwargs["proxy"] = parse_proxy_url_for_playwright(proxy)

                    browser = p.chromium.launch(**launch_kwargs)
                    context = browser.new_context(user_agent=UA, ignore_https_errors=True)
                    page = context.new_page()

                    log(f"Navegando a {url}" + (f" con proxy {proxy}" if proxy else ""))
                    page.goto(url, wait_until="domcontentloaded", timeout=35000)

                    # Enfocar la pestaña Agenda y su contenido
                    ensure_agenda_tab(page)

                    # Esperar filas cabecera de evento
                    try:
                        page.wait_for_selector("#agendaTab tr.event-row[data-event-id]", timeout=15000)
                    except PWTimeout:
                        try: page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        except Exception: pass
                        page.wait_for_selector("#agendaTab tr.event-row[data-event-id]", timeout=8000)

                    last_page_dump = page.content()
                    _debug_write("debug_page_content.html", last_page_dump)

                    event_rows = find_event_rows(page)
                    count = event_rows.count()

                    # Límite para depuración
                    effective = count if MAX_EVENTS <= 0 else min(count, MAX_EVENTS)
                    log(f"Eventos detectados (agenda): {count} | Procesando: {effective} (MAX_EVENTS={MAX_EVENTS})")

                    if effective == 0:
                        raise PWTimeout("Sin eventos tras renderizado (agenda)")

                    # Procesar cada evento (limitado por MAX_EVENTS)
                    for i in range(effective):
                        ev = event_rows.nth(i)
                        event_id = (ev.get_attribute("data-event-id") or "").strip()
                        if not event_id:
                            continue

                        # Desplegar el detalle SOLO de este evento
                        expand_event_detail(page, ev)

                        # HTML de los links del detalle del MISMO evento
                        links_html = get_stream_links_html_for_event(page, event_id)
                        if not links_html:
                            if DEBUG: log(f"[DEBUG] Sin stream-links para: {event_id}")
                            continue

                        ace_ids = extract_ids_from_stream_links_html(links_html)
                        if DEBUG: log(f"[DEBUG] Evento '{event_id}' -> acestream_ids: {ace_ids}")
                        if not ace_ids:
                            continue

                        # Grupo: fecha + competición (desde fila cabecera)
                        ev_html = ev.inner_html()
                        comp = extract_competition_from_html(ev_html)
                        date_str = extract_near_date_str_from_html(ev_html)
                        group_title = normalize_space(f"{date_str} {comp}".strip())

                        for ace_id in ace_ids:
                            display = event_id if not INCLUDE_ID_SUFFIX else f"{event_id} ({ace_id[:3]})"
                            line1 = f'#EXTINF:-1 group-title="{group_title}" tvg-name="{display}",{display}'
                            line2 = f"{ACE_HTTP_PREFIX}{ace_id}"
                            entries.append(f"{line1}\n{line2}")

                    if entries:
                        success = True
                        break

                except Exception as ex:
                    log(f"Intento fallido con {gw} (proxy={proxy}): {ex}")
                finally:
                    if context:
                        try: context.close()
                        except Exception: pass
                    if browser:
                        try: browser.close()
                        except Exception: pass

            if success:
                break

    # Construcción del M3U
    lines = [M3U_HEADER_1, M3U_HEADER_2, ""]
    seen = set()
    for e in entries:
        if e not in seen:
            lines.append(e); seen.add(e)
    m3u = "\n".join(lines).strip() + "\n"

    write_if_changed(m3u, Path(OUTPUT_FILE), Path(HISTORY_DIR), keep_last=50)

    if DEBUG:
        _debug_write("debug_final_m3u.txt", m3u)


if __name__ == "__main__":
    main()
