import os
import sys
import re
import csv
import time
import glob
import datetime
import requests
import cloudscraper
from bs4 import BeautifulSoup
from pathlib import Path
import io

# --- GESTIÓN DEL MODO TESTING ---
# Detectamos si se ha pasado el argumento --testing al script
TEST_MODE = "--testing" in sys.argv
SUFFIX = "_testing" if TEST_MODE else ""

if TEST_MODE:
    print("!!! EJECUTANDO EN MODO TESTING !!!")
    print(f"Las URLs de origen son las de PRODUCCIÓN.")
    print(f"Los archivos resultantes llevarán el sufijo '{SUFFIX}'")

# --- CONFIGURACIÓN DE RUTAS Y NOMBRES DINÁMICOS ---
DIR_CANALES = "canales"
DIR_HISTORY = "history"

# Función auxiliar para inyectar el sufijo antes de la extensión
def get_path(filename):
    base, ext = os.path.splitext(filename)
    # Si el archivo está en una carpeta (ej: canales/lista.csv), manejamos el nombre
    if "/" in base:
        folder, name = base.rsplit("/", 1)
        return f"{folder}/{name}{SUFFIX}{ext}"
    return f"{base}{SUFFIX}{ext}"

# Definición de archivos DE SALIDA (Aquí aplicamos el sufijo)
FILE_ELCANO = get_path("elcano.m3u")
FILE_NEW_ERA = get_path("new_era.m3u")
FILE_EZDAKIT = get_path("ezdakit.m3u")
FILE_EVENTOS = get_path("ezdakit_eventos.m3u")

# Archivos dentro de carpeta canales
FILE_BLACKLIST = get_path(f"{DIR_CANALES}/lista_negra.csv")
FILE_CSV_OUT = get_path(f"{DIR_CANALES}/correspondencias.csv")
FILE_DIAL_MAP = f"{DIR_CANALES}/listado_canales.csv" # Este es de lectura, usamos siempre el original

# --- URLS DE ORIGEN (SIEMPRE LAS DE PRODUCCIÓN) ---
IPNS_HASH = "k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004"

# He añadido más espejos para evitar el error de descarga
URLS_ELCANO = [
    "https://ipfs.io/ipns/k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr/hashes.m3u",
    "https://gateway.pinata.cloud/ipns/k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr/hashes.m3u",
    "https://k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr.ipns.dweb.link/hashes.m3u",
    "https://cloudflare-ipfs.com/ipns/k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr/hashes.m3u"
]

URLS_NEW_ERA = [
    f"https://ipfs.io/ipns/{IPNS_HASH}/data/listas/lista_iptv.m3u",
    f"https://gateway.pinata.cloud/ipns/{IPNS_HASH}/data/listas/lista_iptv.m3u",
    f"https://{IPNS_HASH}.ipns.dweb.link/data/listas/lista_iptv.m3u",
    f"https://cloudflare-ipfs.com/ipns/{IPNS_HASH}/data/listas/lista_iptv.m3u"
]

URLS_AGENDA = [
    f"https://ipfs.io/ipns/{IPNS_HASH}/?tab=agenda",
    f"https://cf-ipfs.com/ipns/{IPNS_HASH}/?tab=agenda",
    f"https://{IPNS_HASH}.ipns.dweb.link/?tab=agenda"
]

HEADER_M3U = """#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/master/guiatv.xml" refresh="3600"
#EXTVLCOPT:network-caching=1000
"""

# ==========================================
# UTILIDADES
# ==========================================

def download_file(urls, output_filename):
    print(f"[DESCARGA] Iniciando descarga hacia -> {output_filename}")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    
    for url in urls:
        try:
            # print(f"  - Probando: {url}") # Descomentar para ver cada intento
            r = session.get(url, timeout=25)
            
            if r.status_code == 200:
                # Verificación básica de que es un M3U
                if "#EXTM3U" in r.text[:200]:
                    Path(output_filename).write_text(r.text, encoding='utf-8')
                    print(f"  [ÉXITO] Descargado correctamente desde {url[:40]}...")
                    return True
                else:
                    print(f"  [AVISO] {url} devolvió 200 pero no parece un M3U válido (Header incorrecto).")
            else:
                print(f"  [FALLO] {url} devolvió Status Code: {r.status_code}")
                
        except Exception as e:
            print(f"  [ERROR] {url}: {e}")
            
    print(f"[ERROR FATAL] Imposible descargar {output_filename} desde ninguna fuente.")
    return False

def read_file_safe(path_obj):
    if not path_obj.exists(): return ""
    raw = path_obj.read_bytes()
    try:
        content = raw.decode('utf-8')
        if "Ã" in content: raise ValueError()
        return content
    except:
        return raw.decode('latin-1', errors='ignore')

def load_blacklist():
    bl = {}
    path = Path(FILE_BLACKLIST)
    if not path.exists():
        if TEST_MODE:
            print(f"[TESTING] No existe {FILE_BLACKLIST}. Se procede sin filtrar canales.")
        return bl
    
    content = read_file_safe(path)
    f = io.StringIO(content)
    reader = csv.DictReader(f)
    for row in reader:
        aid = row.get('ace_id')
        real = row.get('canal_real')
        if aid:
            bl[aid.strip()] = real.strip() if real else ""
    print(f"[INFO] Lista negra ({FILE_BLACKLIST}) cargada: {len(bl)} entradas.")
    return bl

def determine_quality(name):
    u_name = name.upper()
    if "4K" in u_name or "UHD" in u_name:
        return " (UHD)"
    if "1080" in u_name or "FHD" in u_name:
        return " (FHD)"
    return " (HD)"

def clean_channel_name_csv(name, ace_id_suffix):
    if not name: return ""
    name = re.sub(r'-->.*', '', name)
    terms = [
        r'1080p', r'720p', r'FHD', r'UHD', r'4K', r'8K', 
        r'HD', r'SD',
        r'50fps', r'HEVC', r'AAC', r'H\.265',
        r'\(ES\)', r'\(SP\)', r'\(RU\)', r'\(M\d+\)', r'\(O\d+\)', 
        r'\(BACKUP\)', r'\|', r'vip', r'premium', r'\( original \)'
    ]
    for term in terms:
        name = re.sub(term, '', name, flags=re.IGNORECASE)
    name = name.replace('  ', ' ').strip().rstrip(' -_')
    if ace_id_suffix and name.endswith(ace_id_suffix):
        name = name[:-4].strip()
    name = re.sub(r'\s+[0-9a-fA-F]{4}$', '', name)
    return name

def parse_m3u_file(file_path, source_tag=""):
    data = {}
    path = Path(file_path)
    if not path.exists(): return data
    
    content = read_file_safe(path)
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            inf = line
            url = None
            for k in range(i+1, len(lines)):
                if lines[k].strip() and not lines[k].startswith("#"):
                    url = lines[k].strip(); break
            if url:
                m = re.search(r"(?:acestream://|id=|/)([0-9a-fA-F]{40})", url)
                if m:
                    aid = m.group(1)
                    mt = re.search(r'tvg-id="([^"]+)"', inf)
                    mg = re.search(r'group-title="([^"]+)"', inf)
                    raw_name = inf.split(',')[-1].strip()
                    
                    data[aid] = {
                        'name': raw_name,
                        'tvg': mt.group(1).strip() if mt else "Unknown",
                        'group': mg.group(1).strip() if mg else "OTROS",
                        'url': url,
                        'source': source_tag
                    }
        i += 1
    return data

# ==========================================
# MÓDULO 1: FUSIÓN DE LISTAS
# ==========================================

def generate_ezdakit(blacklist_map):
    print(f"\n--- GENERANDO {FILE_EZDAKIT} ---")
    data_elcano = parse_m3u_file(FILE_ELCANO, "E")
    data_newera = parse_m3u_file(FILE_NEW_ERA, "N")
    
    new_era_names = {v['name']: v['tvg'] for v in data_newera.values() if v['tvg'] != "Unknown"}
    merged = data_newera.copy()
    
    for aid, info in data_elcano.items():
        if aid not in merged:
            if info['tvg'] == "Unknown" or not info['tvg']:
                if info['name'] in new_era_names:
                    info['tvg
