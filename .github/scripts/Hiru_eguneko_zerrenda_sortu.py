
# -*- coding: utf-8 -*-
import os, re, sys, hashlib, json
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse, urlencode, urlunparse, parse_qsl

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# =========================
# Configuración por entorno
# =========================
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

# 0 => sin límite; >0 => procesa sólo N primeros
MAX_EVENTS = _get_int_env("MAX_EVENTS", 0)

# Fallback: permitir M3U con IDs aunque no haya Agenda
FALLBACK_ANY_OPENACE = os.environ.get("FALLBACK_ANY_OPENACE", "true").lower() == "true"

# Gateways IPFS en orden
IPFS_GATEWAYS = [
    "https://cloudflare-ipfs.com",
    "https://dweb.link",
    "https://cf-ipfs.com",
    "https://ipfs.runfission.com",
]
if ALLOW_IPFS_IO:
    IPFS_GATEWAYS.append("https://ipfs.io")

# Cabeceras M3U
M3U_HEADER_1 = '#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/EPG_dobleM.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"'
M3U_HEADER_2 = "#EXTVLCOPT:network-caching=1000"
ACE_HTTP_PREFIX = "http://127.0.0.1:6878/ace/getstream?id="

# Regex
HEX40 = r"[a-fA-F0-9]{40}"
OPENACE_RE = re.compile(r"openAcestream\('\"['\"]\)", re.I)
DATE_TOKEN_RE = re.compile(r"\b(\d{2})/-\b")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36 M3U-Bot/1.8"

def log(msg: str): print(f"[m3u] {msg}", flush=True)

def build_url_for_gateway(base_gateway: str, original_url: str) -> str:
    u = urlparse(original_url)
    # conservamos path+query del original, pero con host del gateway
    return base_gateway.rstrip("/") + u.path + (("?" + u.query) if u.query else "")

def add_or_replace_query(url: str, **params) -> str:
    u = urlparse(url)
    qs = dict(parse_qsl(u.query, keep_blank_values=True))
    qs.update({k: v for k, v in params.items() if v is not None})
    new_qs = urlencode(qs, doseq=True)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_qs, u.fragment))

def _debug_write(name: str, content: str | bytes):
    if not DEBUG: return
    d = Path(".debug"); d.mkdir(parents=True, exist_ok=True)
    p = d / name
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content or "", encoding="utf-8", errors="ignore")

def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def extract_near_date_str_from_html(fragment_html: str) -> str:
    try:
        soup = BeautifulSoup(fragment_html or "", "lxml")
        txt = normalize_space(soup.get_text(" ", strip=True))
        m = DATE_TOKEN_RE.search(txt)
        if m: return f"{m.group(1)}-{m.group(2)}"
    except Exception:
        pass
    # fallback: hoy (UTC) si no detectamos
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
        path_out.write_bytes(new_bytes); log(f"Actualizado {path_out}")
    else:
        log("Sin cambios en el fichero principal.")

    # histórico
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

    # limpieza
    history_files = sorted(history_dir.glob("zz_eventos_ott_*.m3u"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
    for old in history_files[keep_last:]:
        try: old.unlink(missing_ok=True)
        except Exception: pass

# ==========================
# Utilidades específicas UI
# ==========================
def neutralize_blocking_modals(page):
    try:
        page.add_style_tag(content="""
          .file-modal, .modal, .toast { display: none !important; visibility: hidden !important; }
          #mainNav { position: relative !important; z-index: 1 !important; }
        """)
    except Exception:
        pass

def force_query_tab_agenda(page, url_current: str) -> str:
    """
    Garantiza ?tab=agenda en la URL (misma gateway).
    Si no coincide, navega y retorna la URL efectiva.
    """
    try:
        if "tab=agenda" not in urlparse(url_current).query:
            new_url = add_or_replace_query(url_current, tab="agenda")
            page.goto(new_url, wait_until="domcontentloaded", timeout=45000)
            return new_url
    except Exception:
        pass
    return url_current

def force_activate_agenda(page):
    # Marca la pestaña Agenda
    page.evaluate("""
      () => {
        const ids = ['canalesTab','agendaTab','descargasTab','buscadorTab','listaPlanaTab','consejosTab'];
        ids.forEach(id => {
          const el = document.getElementById(id);
          if (el) el.classList.remove('active');
        });
        const ag = document.getElementById('agendaTab');
        if (ag) ag.classList.add('active');

        const navBtns = document.querySelectorAll('nav [data-tab]');
        navBtns.forEach(b => b.classList.toggle('active', b.getAttribute('data-tab') === 'agendaTab'));
      }
    """)

def click_all_date_buttons(page):
    try:
        btns = page.locator("#agendaTab .date-btn")
        n = btns.count()
        for i in range(min(n, 7)):
            try:
                btns.nth(i).click(timeout=1500, force=True)
            except Exception:
                pass
    except Exception:
        pass

def find_event_rows(page):
    container = page.locator("#agendaTab")
    table = container.locator(".events-table")
    if table.count() > 0:
        return table.locator("tr.event-row[data-event-id]")
    return container.locator("tr.event-row[data-event-id]")

def expand_event_detail(page, event_row):
    try:
        event_row.click(timeout=2000, force=True)
    except Exception:
        toggles = event_row.locator("[data-bs-target], [data-target], [aria-controls], a[href^='#'], button[aria-controls]")
        for i in range(min(3, toggles.count())):
            try: toggles.nth(i).click(timeout=800, force=True)
            except Exception: pass

def get_stream_links_html_for_event(page, event_id: str) -> Optional[str]:
    try:
        page.wait_for_selector(f"#agendaTab tr.event-detail[data-event-id='{event_id}']",
                               timeout=6000, state="attached")
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
    if not html: return []
    ids = set(OPENACE_RE.findall(html))
    try:
        frag = BeautifulSoup(html, "lxml")
        for a in frag.select("a.stream-link[onclick]"):
            m = OPENACE_RE.search(a.get("onclick", ""))
            if m: ids.add(m.group(1))
    except Exception:
        pass
    return sorted(i.lower() for i in ids)

def extract_ids_anywhere_from_dom(page) -> List[str]:
    """
    Fallback: busca cualquier openAcestream('<ID>') en TODO el HTML.
    """
    html = page.content()
    _debug_write("debug_page_content_fallback.html", html)
    ids = sorted(set(i.lower() for i in OPENACE_RE.findall(html)))
    return ids

# =====================
# Registro de diagnóst.
# =====================
def attach_console_and_network_logging(page):
    logs = []

    def on_console(msg):
        try:
            logs.append({"type": msg.type(), "text": msg.text()})
        except Exception:
            pass
    page.on("console", on_console)

    net = []
    def on_req_finished(req):
        try:
            res = req.response()
            net.append({
                "url": req.url,
                "method": req.method,
                "status": res.status if res else None,
                "ok": res.ok if res else None,
                "resource": req.resource_type
            })
        except Exception:
            pass
    def on_req_failed(req):
        try:
            net.append({
                "url": req.url,
                "method": req.method,
                "failed": True,
                "failure": req.failure,
                "resource": req.resource_type
            })
        except Exception:
            pass

    page.on("requestfinished", on_req_finished)
    page.on("requestfailed", on_req_failed)

    def flush():
        if DEBUG:
            _debug_write("console.log", "\n".join(f"[{l['type']}] {l['text']}" for l in logs))
            _debug_write("network.ndjson", "\n".join(json.dumps(n, ensure_ascii=False) for n in net))

    return flush

# ==============
# Programa ppal.
# ==============
def main():
    if not TARGET_URL:
        log("TARGET_URL vacío"); sys.exit(1)

    entries: List[str] = []
    with sync_playwright() as p:
        gateways = IPFS_GATEWAYS[:]
        proxies = [None] + PROXY_LIST if PROXY_LIST else [None]
        success = False

        for gw in gateways:
            base_url = build_url_for_gateway(gw, TARGET_URL)
            for proxy in proxies:
                browser = context = None
                flush_logs = None
                try:
                    launch_kwargs = {"headless": True}
                    if proxy:
                        launch_kwargs["proxy"] = parse_proxy_url_for_playwright(proxy)

                    browser = p.chromium.launch(**launch_kwargs)
                    context = browser.new_context(user_agent=UA, ignore_https_errors=True)
                    page = context.new_page()
                    page.set_default_timeout(60000)  # + robusto

                    flush_logs = attach_console_and_network_logging(page)

                    log(f"Navegando a {base_url}" + (f" con proxy {proxy}" if proxy else ""))
                    page.goto(base_url, wait_until="domcontentloaded", timeout=60000)

                    # Forzamos modal off + tab agenda + query tab=agenda
                    neutralize_blocking_modals(page)
                    current = page.url
                    current = force_query_tab_agenda(page, current)
                    neutralize_blocking_modals(page)  # otra vez tras posible reload
                    force_activate_agenda(page)

                    # Espera del contenedor agenda
                    page.wait_for_selector("#agendaTab", timeout=20000)

                    # Intento real de click en el botón de nav (por si hay lógica)
                    try:
                        btn = page.locator('nav [data-tab="agendaTab"]')
                        if btn.count() > 0:
                            btn.first.click(timeout=2000, force=True)
                    except Exception:
                        pass

                    # Espera filas (60s máx)
                    try:
                        page.wait_for_function(
                            "document.querySelectorAll('#agendaTab tr.event-row[data-event-id]').length > 0",
                            timeout=60000
                        )
                    except Exception:
                        # Intentamos disparar fechas
                        click_all_date_buttons(page)
                        try:
                            page.wait_for_function(
                                "document.querySelectorAll('#agendaTab tr.event-row[data-event-id]').length > 0",
                                timeout=20000
                            )
                        except Exception:
                            pass

                    # DUMPs de depuración
                    _debug_write("debug_page_content.html", page.content())
                    try:
                        ag_html = page.locator("#agendaTab").inner_html()
                        _debug_write("debug_agenda_only.html", ag_html)
                    except Exception:
                        pass

                    # Conteos
                    try:
                        total_all = page.locator("tr.event-row").count()
                        total_scoped = page.locator("#agendaTab tr.event-row[data-event-id]").count()
                        log(f"Diagnóstico filas -> total página: {total_all} | en #agendaTab: {total_scoped}")
                    except Exception:
                        total_scoped = 0

                    # ========== Camino principal ==========
                    event_rows = find_event_rows(page)
                    count = event_rows.count()
                    effective = count if MAX_EVENTS <= 0 else min(count, MAX_EVENTS)
                    log(f"Eventos detectados (agenda): {count} | Procesando: {effective} (MAX_EVENTS={MAX_EVENTS})")

                    if effective > 0:
                        for i in range(effective):
                            ev = event_rows.nth(i)
                            event_id = (ev.get_attribute("data-event-id") or "").strip()
                            if not event_id:
                                continue

                            expand_event_detail(page, ev)
                            links_html = get_stream_links_html_for_event(page, event_id)
                            if not links_html:
                                continue

                            ace_ids = extract_ids_from_stream_links_html(links_html)
                            if DEBUG:
                                log(f"[DEBUG] Evento '{event_id}' -> IDs: {ace_ids}")
                            if not ace_ids:
                                continue

                            ev_html = ev.inner_html()
                            comp = extract_competition_from_html(ev_html)
                            date_str = extract_near_date_str_from_html(ev_html)
                            group_title = normalize_space(f"{date_str} {comp}".strip()) or "AGENDA"

                            for ace_id in ace_ids:
                                display = event_id if not INCLUDE_ID_SUFFIX else f"{event_id} ({ace_id[:3]})"
                                line1 = f'#EXTINF:-1 group-title="{group_title}" tvg-name="{display}",{display}'
                                line2 = f"{ACE_HTTP_PREFIX}{ace_id}"
                                entries.append(f"{line1}\n{line2}")

                        if entries:
                            success = True
                            break

                    # ========== Fallback (DOM completo) ==========
                    if FALLBACK_ANY_OPENACE:
                        log("Aplicando fallback: escaneo global de openAcestream(...)")
                        ids_any = extract_ids_anywhere_from_dom(page)
                        if ids_any:
                            for ace_id in (ids_any if MAX_EVENTS <= 0 else ids_any[:MAX_EVENTS]):
                                display = f"ID {ace_id[:8]}…" if INCLUDE_ID_SUFFIX else f"{ace_id}"
                                line1 = f'#EXTINF:-1 group-title="AGENDA (fallback)" tvg-name="{display}",{display}'
                                line2 = f"{ACE_HTTP_PREFIX}{ace_id}"
                                entries.append(f"{line1}\n{line2}")
                            success = True
                            break
                        else:
                            log("Fallback sin resultados (no se detectaron openAcestream en el DOM).")

                except Exception as ex:
                    log(f"Intento fallido con gateway={gw} proxy={proxy}: {ex}")
                finally:
                    try:
                        if flush_logs: flush_logs()
                    except Exception:
                        pass
                    if context:
                        try: context.close()
                        except Exception: pass
                    if browser:
                        try: browser.close()
                        except Exception: pass

            if success:
                break

    # Construcción M3U
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
