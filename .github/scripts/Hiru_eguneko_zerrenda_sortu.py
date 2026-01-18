
# -*- coding: utf-8 -*-
import os
import re
import sys
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse, urljoin

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

# Gateways alternativos a ipfs.io; se probarán en orden con Playwright
IPFS_GATEWAYS = [
    "https://cloudflare-ipfs.com",
    "https://dweb.link",
    "https://cf-ipfs.com",
    "https://ipfs.runfission.com",
]
if ALLOW_IPFS_IO:
    IPFS_GATEWAYS.append("https://ipfs.io")  # último recurso

M3U_HEADER_1 = '#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/EPG_dobleM.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"'
M3U_HEADER_2 = "#EXTVLCOPT:network-caching=1000"
ACE_HTTP_PREFIX = "http://127.0.0.1:6878/ace/getstream?id="

HEX40_RE = re.compile(r"\b[a-fA-F0-9]{40}\b")
ACE_URL_RE = re.compile(r"acestream://([a-fA-F0-9]{40})", re.IGNORECASE)
DATE_TOKEN_RE = re.compile(r"\b(\d{2})/-\b")
STREAM_LINKS_CLASS_RE = re.compile(r"\bstream[-_\s]*links\b", re.IGNORECASE)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36 M3U-Bot/1.5"


def log(msg: str):
    print(f"[m3u] {msg}", flush=True)


def build_url_for_gateway(base_gateway: str, original_url: str) -> str:
    u = urlparse(original_url)
    path, qs = u.path, u.query
    base = base_gateway.rstrip("/")
    return f"{base}{path}" + (f"?{qs}" if qs else "")


def _debug_write(name: str, content: str):
    if not DEBUG:
        return
    d = Path(".debug")
    d.mkdir(parents=True, exist_ok=True)
    Path(d / name).write_text(content or "", encoding="utf-8", errors="ignore")


def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def extract_near_date_str_from_html(fragment_html: str) -> str:
    """Busca DD-MM o DD/MM en el HTML del evento; fallback: hoy UTC."""
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


def extract_ace_ids_from_stream_html(stream_html: str) -> List[str]:
    ids = set()
    if not stream_html:
        return []
    # en texto/HTML
    for m in ACE_URL_RE.findall(stream_html):
        ids.add(m.lower())
    for m in HEX40_RE.findall(stream_html):
        ids.add(m.lower())
    # también mirar atributos con BeautifulSoup
    try:
        frag = BeautifulSoup(stream_html, "lxml")
        for tag in frag.find_all(True):
            for k, v in (tag.attrs or {}).items():
                vals = v if isinstance(v, (list, tuple)) else [v]
                for val in vals:
                    if not val:
                        continue
                    val = str(val)
                    m = ACE_URL_RE.search(val)
                    if m:
                        ids.add(m.group(1).lower())
                    else:
                        m2 = HEX40_RE.search(val)
                        if m2:
                            ids.add(m2.group(0).lower())
    except Exception:
        pass
    return sorted(ids)


def find_stream_container_html_for_event(page, event_element) -> Optional[str]:
    """
    Devuelve el HTML del contenedor 'stream-links' correspondiente a un evento:
      1) dentro del propio nodo
      2) en panel colapsable referenciado por data-bs-target/aria-controls/href="#id"
      3) en hermanos siguientes hasta el próximo evento
    """
    js = """
    (tr) => {
      function hasStreamLinks(el) {
        if (!el) return null;
        // match por clase exacta o "contiene"
        let q = el.querySelector('.stream-links');
        if (q) return q;
        // aproximado por clase que contenga "stream" y "links"
        let all = el.querySelectorAll('[class]');
        for (let node of all) {
          const cls = (node.getAttribute('class') || '').toLowerCase();
          if (cls.includes('stream') && cls.includes('links')) {
            return node;
          }
        }
        return null;
      }

      // 1) Dentro del propio evento
      let inside = hasStreamLinks(tr);
      if (inside) return inside.outerHTML;

      // 2) Panel colapsable por id
      const toggles = tr.querySelectorAll('[data-bs-target], [data-target], [aria-controls], a[href^="#"]');
      for (let el of toggles) {
        let id = el.getAttribute('data-bs-target') || el.getAttribute('data-target') || el.getAttribute('aria-controls') || '';
        if (!id && el.tagName.toLowerCase() === 'a') {
          const href = el.getAttribute('href') || '';
          if (href.startsWith('#')) id = href.slice(1);
        }
        if (id) {
          const panel = document.getElementById(id);
          if (panel) {
            let target = hasStreamLinks(panel) || panel;
            if (target) return target.outerHTML;
          }
        }
      }

      // 3) Hermanos siguientes hasta el próximo evento
      let sib = tr.nextElementSibling;
      while (sib) {
        if (sib.hasAttribute('data-event-id')) break;
        let found = hasStreamLinks(sib);
        if (found) return found.outerHTML;
        sib = sib.nextElementSibling;
      }
      return null;
    }
    """
    try:
        return page.evaluate(js, event_element)
    except Exception:
        return None


def parse_proxy_url(proxy_url: str) -> dict:
    """
    Convierte http(s)://user:pass@host:port en el dict esperado por Playwright.
    """
    u = urlparse(proxy_url)
    cfg = {"server": f"{u.scheme}://{u.hostname}:{u.port or 80}"}
    if u.username:
        cfg["username"] = u.username
    if u.password:
        cfg["password"] = u.password
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
    if not TARGET_URL:
        log("TARGET_URL vacío"); sys.exit(1)

    entries: List[str] = []
    last_page_dump = ""

    with sync_playwright() as p:
        # Intentamos gateways y proxies en cascada
        gateways = IPFS_GATEWAYS[:]
        proxies = [None] + PROXY_LIST if PROXY_LIST else [None]

        success = False
        for gw in gateways:
            url = build_url_for_gateway(gw, TARGET_URL)
            for proxy in proxies:
                browser = None
                context = None
                try:
                    launch_kwargs = {"headless": True}
                    if proxy:
                        launch_kwargs["proxy"] = parse_proxy_url(proxy)

                    browser = p.chromium.launch(**launch_kwargs)
                    context = browser.new_context(user_agent=UA, ignore_https_errors=True)
                    page = context.new_page()

                    log(f"Navegando a {url}" + (f" con proxy {proxy}" if proxy else ""))
                    page.goto(url, wait_until="domcontentloaded", timeout=35000)

                    # Espera tentativa de la pestaña Agenda: algunos frameworks tardan
                    # Intentamos detectar al menos un [data-event-id]
                    try:
                        page.wait_for_selector("[data-event-id]", timeout=15000)
                    except PWTimeout:
                        # Scroll para disparar cargas diferidas
                        try:
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        except Exception:
                            pass
                        # segunda oportunidad
                        page.wait_for_selector("[data-event-id]", timeout=10000)

                    # volcamos el HTML de la página para depurar si hace falta
                    last_page_dump = page.content()
                    _debug_write("debug_page_content.html", last_page_dump)

                    # Recogemos todos los eventos
                    event_loc = page.locator("[data-event-id]")
                    count = event_loc.count()
                    log(f"Eventos detectados (render): {count}")

                    # Si aún 0, probamos expandir algo genérico (por si hay controles globales)
                    if count == 0:
                        # botoncitos que puedan cargar/mostrar agenda
                        candidates = page.locator('[data-bs-target], [data-target], [aria-controls], a[href^="#"], button')
                        for i in range(min(50, candidates.count())):
                            try:
                                candidates.nth(i).click(timeout=1000)
                            except Exception:
                                pass
                        # reintentar
                        event_loc = page.locator("[data-event-id]")
                        count = event_loc.count()
                        log(f"Eventos detectados tras intentar expandir: {count}")

                    if count == 0:
                        # Cambiamos de proxy/gateway
                        raise PWTimeout("Sin eventos tras renderizado")

                    # Expandimos y extraemos por evento
                    for i in range(count):
                        ev = event_loc.nth(i)
                        event_id = ev.get_attribute("data-event-id") or ""
                        event_id = (event_id or "").strip()
                        if not event_id:
                            continue

                        # Intento de clic en toggles DENTRO del evento
                        toggles = ev.locator("[data-bs-target], [data-target], [aria-controls], a[href^='#'], button[aria-controls]")
                        tcount = toggles.count()
                        for t in range(min(8, tcount)):
                            try:
                                toggles.nth(t).click(timeout=1000)
                            except Exception:
                                pass

                        # Localizar el contenedor stream-links correspondiente
                        html_stream = find_stream_container_html_for_event(page, ev.element_handle())
                        if not html_stream:
                            # Por si requiere scroll un poco más
                            try:
                                ev.scroll_into_view_if_needed(timeout=2000)
                            except Exception:
                                pass
                            html_stream = find_stream_container_html_for_event(page, ev.element_handle())

                        if not html_stream:
                            if DEBUG:
                                log(f"[DEBUG] Sin stream-links para: {event_id}")
                            continue

                        ace_ids = extract_ace_ids_from_stream_html(html_stream)
                        if not ace_ids:
                            if DEBUG:
                                log(f"[DEBUG] Sin acestream_id en stream-links para: {event_id}")
                            continue

                        # info de grupo: fecha + competición
                        event_html = ev.inner_html()
                        comp = extract_competition_from_html(event_html)
                        date_str = extract_near_date_str_from_html(event_html)
                        group_title = normalize_space(f"{date_str} {comp}".strip())

                        for ace_id in ace_ids:
                            display = event_id if not INCLUDE_ID_SUFFIX else f"{event_id} ({ace_id[:3]})"
                            line1 = f'#EXTINF:-1 group-title="{group_title}" tvg-name="{display}",{display}'
                            line2 = f"{ACE_HTTP_PREFIX}{ace_id}"
                            entries.append(f"{line1}\n{line2}")

                    if entries:
                        success = True
                        break  # salimos del bucle de proxies para este gateway

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
    lines.extend(entries)
    m3u = "\n".join(lines).strip() + "\n"

    # Guardado e histórico
    write_if_changed(m3u, Path(OUTPUT_FILE), Path(HISTORY_DIR), keep_last=50)

    # Depuración adicional
    if DEBUG and last_page_dump:
        _debug_write("debug_final_m3u.txt", m3u)


if __name__ == "__main__":
    main()
