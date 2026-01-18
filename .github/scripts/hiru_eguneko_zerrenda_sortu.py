
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import hashlib
import shutil
import random
import datetime
from typing import List, Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# -------------------------
# CONFIGURACIÓN
# -------------------------

SOURCE_URL = "https://ipfs.io/ipns/k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004/?tab=agenda"

# Gateways "proxy" alternativos para evitar el dominio original ipfs.io
IPFS_GATEWAYS = [
    "https://cloudflare-ipfs.com",
    "https://cf-ipfs.com",
    "https://gateway.pinata.cloud",
    "https://dweb.link",
    "https://w3s.link",
    "https://ipfs.runfission.com",
    # Como último recurso, el original (se intentará solo al final):
    "https://ipfs.io",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )
}

TIMEOUT = 20  # segundos

# Archivo de salida e histórico
OUTPUT_FILE = "zz_eventos_all_ott.m3u"
HISTORY_DIR = "history"
MAX_HISTORY = 50

# Cabeceras M3U (exactamente como solicitaste)
M3U_HEADER_1 = (
    '#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml,'
    'https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/EPG_dobleM.xml,'
    'https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"'
)
M3U_HEADER_2 = "#EXTVLCOPT:network-caching=1000"

# Regex útiles
RE_ACE = re.compile(r'(?i)(?:acestream://)?([0-9a-f]{40})')
RE_TIME = re.compile(r'\b([01]\d|2[0-3]):[0-5]\d\b')
RE_DATE_DD_MM = re.compile(r'\b([0-3]\d)-/\b')
RE_CATEGORY_HINTS = re.compile(
    r'\b(Liga|Premier|Serie A|Bundesliga|Copa|Champions|Europa League|Conference|NBA|ACB|Euroliga|ATP|WTA|NFL|MLS|UFC|Formula|Fórmula|MotoGP|Tenis|Baloncesto|Fútbol)\b',
    re.IGNORECASE
)

def hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def ensure_dirs():
    os.makedirs(HISTORY_DIR, exist_ok=True)

def replace_gateway(url: str, new_base: str) -> str:
    # Reemplaza 'https://ipfs.io' por el gateway indicado.
    return url.replace("https://ipfs.io", new_base.rstrip('/'))

def fetch_html_with_gateways(url: str) -> str:
    gateways = IPFS_GATEWAYS[:]
    # Priorizamos gateways alternativos, dejando ipfs.io para el final
    if "https://ipfs.io" in gateways:
        gateways.remove("https://ipfs.io")
        gateways.append("https://ipfs.io")
    random.shuffle(gateways[:-1])  # sólo mezclamos los alternativos

    last_err = None
    for gw in gateways:
        gw_url = replace_gateway(url, gw)
        try:
            resp = requests.get(gw_url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code == 200 and resp.text.strip():
                return resp.text
        except Exception as e:
            last_err = e
            continue
    if last_err:
        raise RuntimeError(f"No se pudo descargar la página desde gateways alternativos. Último error: {last_err}")
    raise RuntimeError("No se pudo descargar la página (respuesta vacía).")

def text_of(el) -> str:
    try:
        return " ".join(el.stripped_strings)
    except Exception:
        return ""

def find_nearest(elt, regex: re.Pattern, max_up: int = 6) -> Optional[str]:
    # Sube por ancestros y busca el primer match del regex en su texto
    cur = elt
    for _ in range(max_up):
        if not cur:
            break
        t = text_of(cur)
        m = regex.search(t)
        if m:
            return m.group(0)
        cur = cur.parent if hasattr(cur, "parent") else None
    return None

def guess_category(elt) -> str:
    # Busca una categoría plausible en el contexto
    cur = elt
    for _ in range(6):
        if not cur:
            break
        t = text_of(cur)
        m = RE_CATEGORY_HINTS.search(t)
        if m:
            return m.group(0).strip()
        # Candidatos por clases/comunes
        if getattr(cur, "attrs", None):
            for k, v in cur.attrs.items():
                if isinstance(v, list):
                    vv = " ".join(v)
                else:
                    vv = str(v)
                mm = RE_CATEGORY_HINTS.search(vv)
                if mm:
                    return mm.group(0).strip()
        cur = cur.parent if hasattr(cur, "parent") else None
    return "Deportes"

def guess_event_name(elt) -> str:
    # Heurística: el heading más próximo o un texto "rico" cercano
    # Intenta con headings primero
    cur = elt
    for _ in range(6):
        if not cur:
            break
        # Busca headings directos
        for h in cur.find_all(["h1", "h2", "h3", "h4", "h5", "h6"], recursive=False):
            htxt = text_of(h)
            if len(htxt) >= 5:
                return htxt
        cur = cur.parent if hasattr(cur, "parent") else None

    # Si no, sube y coge el texto más largo pero razonable
    cur = elt
    best = ""
    for _ in range(6):
        if not cur:
            break
        t = text_of(cur)
        t = re.sub(RE_ACE, "", t)  # quita el id del propio texto
        if 10 <= len(t) <= 200:
            if len(t) > len(best):
                best = t
        cur = cur.parent if hasattr(cur, "parent") else None
    if best:
        return best

    # Último recurso: el texto del propio elemento
    t = text_of(elt)
    return t[:100].strip() if t else "Evento"

def parse_jsonld_events(soup: BeautifulSoup) -> List[Dict]:
    # Si la página publica JSON-LD con @type Event, lo preferimos
    import json
    events = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string)
        except Exception:
            continue

        def handle(obj):
            if isinstance(obj, dict) and obj.get("@type") in ("Event", "SportsEvent"):
                name = obj.get("name")
                start = obj.get("startDate") or obj.get("startTime") or ""
                # Fecha y hora aproximadas
                dd_mm = None
                hh_mm = None
                if isinstance(start, str):
                    # Intenta extraer hora y fecha de ISO
                    m_time = re.search(r'T?([01]\d|2[0-3]):[0-5]\d', start)
                    if m_time:
                        hh_mm = m_time.group(0)[-5:]
                    m_date = re.search(r'(\d{4})-(\d{2})-(\d{2})', start)
                    if m_date:
                        dd_mm = f"{m_date.group(3)}-{m_date.group(2)}"

                # Categoría tentativa por competencia/league
                category = obj.get("superEvent", {}).get("name") if isinstance(obj.get("superEvent"), dict) else None
                if not category:
                    category = "Deportes"

                events.append({
                    "event_name": name or "Evento",
                    "date_dd_mm": dd_mm or "",
                    "time_hh_mm": hh_mm or "",
                    "category": category,
                    # Los canales con acestream_id tendrán que encontrarse por otra vía en HTML
                    "channels": [],
                })

        if isinstance(data, list):
            for item in data:
                handle(item)
        else:
            handle(data)
    return events

def extract_entries(html: str) -> List[Dict]:
    """
    Devuelve una lista de entradas (evento-canal) con:
      - date_dd_mm: 'DD-MM' (si no se encuentra, se intentará dejar vacío o '??-??')
      - time_hh_mm: 'HH:MM' (si no se encuentra, '--:--')
      - category: texto
      - event_name: texto
      - ace_id: 40 hex
    """
    soup = BeautifulSoup(html, "lxml")

    # 1) Intento de JSON-LD solo para evento/fecha/hora/categoría (no suele incluir acestream)
    #    Lo dejamos preparado por si coincide, pero la mayoría de veces tiraremos de HTML.
    #    Si tu página tiene estructura fija, puedo adaptar selectores exactos.
    _ = parse_jsonld_events(soup)

    entries = []
    seen = set()  # para evitar duplicados (event_name, date, time, ace_id)

    # 2) Heurística general: localizar cualquier texto con acestream ID y extraer su contexto
    for text_node in soup.find_all(string=RE_ACE):
        for m in RE_ACE.finditer(text_node):
            ace_id = m.group(1).lower()

            # Nodo base
            base_el = text_node.parent if hasattr(text_node, "parent") else None
            if not base_el:
                continue

            # Hora (HH:MM)
            time_match = find_nearest(base_el, RE_TIME) or "--:--"
            if time_match and ":" in time_match:
                time_hh_mm = time_match[-5:]
            else:
                time_hh_mm = "--:--"

            # Fecha (DD-MM)
            date_match = find_nearest(base_el, RE_DATE_DD_MM)
            date_dd_mm = None
            if date_match:
                dm = RE_DATE_DD_MM.search(date_match)
                if dm:
                    date_dd_mm = f"{dm.group(1)}-{dm.group(2)}"
            if not date_dd_mm:
                # Como último recurso, deja vacío (o podríamos usar hoy). Prefiero no inventar.
                date_dd_mm = "??-??"

            # Categoría
            category = guess_category(base_el)

            # Nombre del evento
            event_name = guess_event_name(base_el)

            key = (event_name, date_dd_mm, time_hh_mm, ace_id)
            if key in seen:
                continue
            seen.add(key)

            entries.append({
                "date_dd_mm": date_dd_mm,
                "time_hh_mm": time_hh_mm,
                "category": category,
                "event_name": event_name,
                "ace_id": ace_id,
            })

    return entries

def build_m3u(entries: List[Dict]) -> str:
    """
    Construye el contenido M3U.
    Formato por entrada:
      #EXTINF:-1 group-title="{DD-MM} {categoria}" tvg-name="{HH:MM} {evento} ({ACE3})",{HH:MM} {evento} ({ACE3})
      http://127.0.0.1:6878/ace/getstream?id={acestream_id}
    """
    lines = []
    lines.append(M3U_HEADER_1)
    lines.append(M3U_HEADER_2)
    lines.append("")  # línea en blanco tercera

    # Orden opcional por fecha/hora/evento
    def sort_key(e):
        # Prioriza fecha conocida y hora, si no, al final
        ddmm = e["date_dd_mm"]
        hhmm = e["time_hh_mm"]
        # Normaliza (??-?? y --:-- al final)
        try:
            dd, mm = ddmm.split("-")
            dd_i = int(dd) if dd.isdigit() else 99
            mm_i = int(mm) if mm.isdigit() else 99
        except Exception:
            dd_i, mm_i = 99, 99
        try:
            hh, mi = hhmm.split(":")
            hh_i = int(hh) if hh.isdigit() else 99
            mi_i = int(mi) if mi.isdigit() else 99
        except Exception:
            hh_i, mi_i = 99, 99
        return (mm_i, dd_i, hh_i, mi_i, e["event_name"].lower())

    entries_sorted = sorted(entries, key=sort_key)

    for e in entries_sorted:
        ddmm = e["date_dd_mm"]
        cat = e["category"].strip()
        hhmm = e["time_hh_mm"]
        name = e["event_name"].strip()
        ace = e["ace_id"]
        ace3 = ace[:3].upper()

        group_title = f'{ddmm} {cat}'.strip()
        channel_name = f'{hhmm} {name} ({ace3})'.strip()

        lines.append(f'#EXTINF:-1 group-title="{group_title}" tvg-name="{channel_name}",{channel_name}')
        lines.append(f'http://127.0.0.1:6878/ace/getstream?id={ace}')

    return "\n".join(lines) + "\n"

def write_if_changed(content: str, path: str) -> bool:
    """
    Escribe el archivo solo si su contenido cambió (devuelve True si cambió).
    """
    new_hash = hash_bytes(content.encode("utf-8"))
    if os.path.exists(path):
        with open(path, "rb") as f:
            existing = f.read()
        if hash_bytes(existing) == new_hash:
            # No cambió
            return False

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True

def update_history(content: str):
    """
    Si el contenido cambió respecto al anterior, guarda una copia en history/
    y limita el histórico a los últimos MAX_HISTORY.
    """
    now = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    hist_name = f"zz_eventos_all_ott_{now}.m3u"
    hist_path = os.path.join(HISTORY_DIR, hist_name)
    with open(hist_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Limitar a MAX_HISTORY (orden por mtime)
    files = [os.path.join(HISTORY_DIR, x) for x in os.listdir(HISTORY_DIR) if x.endswith(".m3u")]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for old in files[MAX_HISTORY:]:
        try:
            os.remove(old)
        except Exception:
            pass

def main():
    ensure_dirs()

    try:
        html = fetch_html_with_gateways(SOURCE_URL)
    except Exception as e:
        print(f"[ERROR] Descarga fallida: {e}", file=sys.stderr)
        sys.exit(1)

    entries = extract_entries(html)

    # Filtrar por seguridad: solo mantener entradas con ace_id (ya lo son)
    entries = [e for e in entries if e.get("ace_id") and len(e["ace_id"]) == 40]

    if not entries:
        # Si no hay entradas, aun así escribimos el M3U con solo cabeceras
        print("[WARN] No se encontraron eventos con acestream_id. Se generará cabecera vacía.")
    content = build_m3u(entries)

    changed = write_if_changed(content, OUTPUT_FILE)
    if changed:
        update_history(content)
        print(f"[OK] Actualizado {OUTPUT_FILE} y añadido a histórico.")
    else:
        print(f"[OK] Sin cambios en {OUTPUT_FILE}. No se añade histórico.")

if __name__ == "__main__":
    main()
``
