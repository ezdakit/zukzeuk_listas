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
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"})
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

# --- Nueva lógica de Scraping Nativo ---
def fetch_equivalencias():
    try:
        r = requests.get("https://kiroideuno.pages.gay/equivalencias_canales.json", timeout=15)
        return r.json()
    except Exception as e:
        log(f"Aviso: No se pudo cargar equivalencias_canales.json ({e})")
        return {}

def scrape_futbolenlatv():
    url = "https://www.futbolenlatv.es/deporte"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    
    soup = BeautifulSoup(r.text, 'html.parser')
    eventos = []
    fecha_actual = "Próximamente"
    
    # Leemos el DOM capturando los Headers de fecha y las Tablas de partidos
    for element in soup.find_all(['h2', 'h3', 'tr']):
        if element.name in ['h2', 'h3']:
            text = element.get_text(strip=True)
            if text: fecha_actual = text
            continue
            
        if element.name == 'tr':
            cols = element.find_all('td')
            if len(cols) >= 4:
                hora = cols[0].get_text(strip=True)
                torneo = cols[1].get_text(strip=True)
                partido = cols[2].get_text(separator=" ", strip=True)
                
                canales = []
                # 1. Buscar en el ALT de las imágenes
                for img in cols[3].find_all('img'):
                    alt = img.get('alt') or img.get('title')
                    if alt: canales.append(alt.strip())
                        
                # 2. Si no hay imágenes, buscar texto plano
                if not canales:
                    txt = cols[3].get_text(separator="|", strip=True)
                    canales = [c.strip() for c in txt.split("|") if c.strip()]
                    
                # Validar que parece un partido real
                if re.match(r'^[0-2]?\d:[0-5]\d$', hora) and partido:
                    eventos.append({
                        "fecha": fecha_actual,
                        "hora": hora,
                        "competicion": torneo,
                        "partido": partido,
                        "canales": canales
                    })
    return eventos

def build_events_m3u(agenda, equivalencias, elcano, path):
    lines, vistos = [], set()
    hash_list = elcano.get('hashes', [])
    
    for e in agenda:
        for web_channel in e['canales']:
            # 1. Mapeo de equivalencias
            standard_name = web_channel
            for key, aliases in equivalencias.items():
                if web_channel in aliases or web_channel == key:
                    standard_name = key
                    break
            
            # 2. Búsqueda flexible en Elcano (hashes.json)
            target_norm = norm(standard_name)
            target_norm = re.sub(r'\(.*?\)', '', target_norm).strip() # Limpiar parentesis
            
            matches = []
            for item in hash_list:
                elcano_title = norm(item.get('title', ''))
                if target_norm in elcano_title or elcano_title in target_norm:
                    matches.append(item)
                    
            # 3. Generar M3U
            for match in matches:
                h = match.get('hash', '').lower()
                if not h: continue
                
                clave = (e['fecha'], e['hora'], e['partido'], web_channel, h)
                if clave in vistos: continue
                vistos.add(clave)
                
                base, calidad, stars = split_title(match.get('title'))
                name = f"{e['hora']} - {e['partido']} ({web_channel})"
                if calidad: name += f" ({calidad})"
                name += f" ({h[:3]})"
                
                group = f"{e['fecha']} | {e['competicion']}"
                
                lines.append(f'#EXTINF:-1 group-title="{attr(group)}" tvg-name="{attr(name)}",{name}')
                lines.append(EVENTS_URL_TEMPLATE.format(hash=h))
                
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
        except:
            elcano = None
        errores.append("elcano")

    # 2. Equivalencias y Agenda (100% nativo)
    if elcano:
        equivalencias = fetch_equivalencias()
        log(f"Equivalencias cargadas: {len(equivalencias)} claves")
        
        try:
            agenda = scrape_futbolenlatv()
            log(f"Agenda descargada: {len(agenda)} eventos encontrados en futbolenlatv.es")
            
            n = build_events_m3u(agenda, equivalencias, elcano, EVENTS_M3U)
            log(f"Guardado {EVENTS_M3U}: {n} entradas generadas")
            
            # Generamos el JSON final como respaldo estructurado
            resultado = {
                "fuente": "futbolenlatv.es/deporte",
                "elcano_cid": elcano_cid,
                "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "agenda": agenda
            }
            write_json(OUTPUT_FILE, resultado)
            log(f"Guardado {OUTPUT_FILE}")
            
        except Exception as e:
            log(f"ERROR construyendo agenda de eventos: {e}")
            errores.append("eventos")
    else:
        log("Sin datos de Elcano no se cruzan eventos.")

    if errores: sys.exit(1)

if __name__ == "__main__":
    main()
