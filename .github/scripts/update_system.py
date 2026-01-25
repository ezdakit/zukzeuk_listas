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
TEST_MODE = "--testing" in sys.argv
SUFFIX = "_testing" if TEST_MODE else ""

if TEST_MODE:
    print("!!! EJECUTANDO EN MODO TESTING !!!")
    print(f"Las URLs de origen son las de PRODUCCIÓN.")
    print(f"Los archivos resultantes llevarán el sufijo '{SUFFIX}'")

# --- CONFIGURACIÓN DE RUTAS Y NOMBRES DINÁMICOS ---
DIR_CANALES = "canales"
DIR_HISTORY = "history"

def get_path(filename):
    base, ext = os.path.splitext(filename)
    if "/" in base:
        folder, name = base.rsplit("/", 1)
        return f"{folder}/{name}{SUFFIX}{ext}"
    return f"{base}{SUFFIX}{ext}"

FILE_ELCANO = get_path("elcano.m3u")
FILE_NEW_ERA = get_path("new_era.m3u")
FILE_EZDAKIT = get_path("ezdakit.m3u")
FILE_EVENTOS = get_path("ezdakit_eventos.m3u")
FILE_BLACKLIST = get_path(f"{DIR_CANALES}/lista_negra.csv")
FILE_CSV_OUT = get_path(f"{DIR_CANALES}/correspondencias.csv")
FILE_DIAL_MAP = f"{DIR_CANALES}/listado_canales.csv"

# --- URLS DE ORIGEN ---
IPNS_HASH = "k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004"

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
            r = session.get(url, timeout=25)
            if r.status_code == 200:
                if "#EXTM3U" in r.text[:200]:
                    Path(output_filename).write_text(r.text, encoding='utf-8')
                    print(f"  [ÉXITO] Descargado correctamente desde {url[:40]}...")
                    return True
                else:
                    print(f"  [AVISO] {url} no parece un M3U válido.")
            else:
                print(f"  [FALLO] {url} Status Code: {r.status_code}")
        except Exception as e:
            print(f"  [ERROR] {url}: {e}")
    print(f"[ERROR FATAL] Imposible descargar {output_filename}")
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
                    info['tvg'] = new_era_names[info['name']]
            merged[aid] = info

    final_items = []
    for aid, info in merged.items():
        prefix = aid[:3]
        quality_suffix = determine_quality(info['name'])
        tvgid = info['tvg']
        
        if tvgid == "Unknown":
            base_name = f"{info['name']}{quality_suffix} ({info['source']}-{prefix})"
        else:
            norm = tvgid[:-3] if tvgid.endswith(" HD") else tvgid
            base_name = f"{norm}{quality_suffix} ({info['source']}-{prefix})"
        
        final_group = info['group']
        final_name = base_name
        
        if aid in blacklist_map:
            final_group = "ZZ_Canales_KO"
            if blacklist_map[aid]:
                final_name = f"{base_name} >>> {blacklist_map[aid]}"
        
        entry = f'#EXTINF:-1 tvg-id="{tvgid}" tvg-name="{final_name}" group-title="{final_group}",{final_name}\n{info["url"]}'
        final_items.append((final_name, entry))
        
    final_items.sort(key=lambda x: x[0])
    
    content = HEADER_M3U + "\n" + "\n".join([item[1] for item in final_items])
    Path(FILE_EZDAKIT).write_text(content, encoding='utf-8')
    print(f"[ÉXITO] Generado {FILE_EZDAKIT} con {len(final_items)} canales.")
    return merged

# ==========================================
# MÓDULO 2: GENERACIÓN DE CSV
# ==========================================

def generate_csv(blacklist_map):
    print(f"\n--- GENERANDO {FILE_CSV_OUT} ---")
    data_elcano = parse_m3u_file(FILE_ELCANO)
    data_newera = parse_m3u_file(FILE_NEW_ERA)
    
    all_ids = set(data_elcano.keys()) | set(data_newera.keys())
    rows = []
    
    for aid in all_ids:
        # Datos Elcano
        ne = data_elcano.get(aid, {}).get('name', '')
        te = data_elcano.get(aid, {}).get('tvg', '')
        ge = data_elcano.get(aid, {}).get('group', '')
        
        # Datos New Era
        nn = data_newera.get(aid, {}).get('name', '')
        tn = data_newera.get(aid, {}).get('tvg', '')
        gn = data_newera.get(aid, {}).get('group', '')
        
        qual = determine_quality(ne + " " + nn).strip().replace("(", "").replace(")", "").strip()
        base = nn if nn else ne
        sup = clean_channel_name_csv(base, aid[-4:])
        
        in_bl = "yes" if aid in blacklist_map else "no"
        real_ch = blacklist_map.get(aid, "")
        
        rows.append({
            'acestream_id': aid,
            'nombre_e': ne, 'nombre_ne': nn,
            'tvg-id_e': te, 'tvg-id_ne': tn,
            'nombre_supuesto': sup,
            'grupo_e': ge, 'grupo_ne': gn,  # Nuevos campos
            'calidad': qual,
            'lista_negra': in_bl,
            'canal_real': real_ch
        })
        
    rows.sort(key=lambda x: x['nombre_supuesto'])
    
    Path(DIR_CANALES).mkdir(exist_ok=True)
    with open(FILE_CSV_OUT, 'w', newline='', encoding='utf-8-sig') as f:
        fields = ['acestream_id', 'nombre_e', 'nombre_ne', 'tvg-id_e', 'tvg-id_ne', 
                  'nombre_supuesto', 'grupo_e', 'grupo_ne', 
                  'calidad', 'lista_negra', 'canal_real']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"[ÉXITO] Generado {FILE_CSV_OUT} con {len(rows)} filas.")

# ==========================================
# MÓDULO 3: SCRAPER DE AGENDA
# ==========================================

def load_dial_mapping():
    mapping = {}
    path = Path(FILE_DIAL_MAP)
    if not path.exists(): return mapping
    
    content = read_file_safe(path)
    f = io.StringIO(content)
    reader = csv.DictReader(f)
    for row in reader:
        dial = row.get('Dial_Movistar(M)')
        tvg_id = row.get('TV_guide_id')
        if dial and tvg_id:
            mapping[dial.strip()] = tvg_id.strip()
    return mapping

def load_ezdakit_streams_for_agenda():
    streams = {}
    if not Path(FILE_EZDAKIT).exists(): return streams
    
    content = Path(FILE_EZDAKIT).read_text(encoding='utf-8')
    pattern = re.compile(r'tvg-id="([^"]+)".*?,([^\n]*)\n.*?([0-9a-fA-F]{40})', re.DOTALL)
    
    for tvg_id, full_name, ace_id in pattern.findall(content):
        if tvg_id == "Unknown": continue
        if tvg_id not in streams: streams[tvg_id] = []
        
        qual = " (HD)"
        if "(UHD)" in full_name: qual = " (UHD)"
        elif "(FHD)" in full_name: qual = " (FHD)"
        
        streams[tvg_id].append({'id': ace_id, 'quality': qual})
    return streams

def scrape_agenda(blacklist_map):
    print("\n--- EJECUTANDO SCRAPER DE EVENTOS ---")
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    
    html = None
    for url in URLS_AGENDA:
        try:
            print(f"Probando {url}...")
            r = scraper.get(url, timeout=60)
            if r.status_code == 200:
                r.encoding = 'utf-8' 
                html = r.text
                break
            else:
                print(f"Fallo: Status {r.status_code}")
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(2)
            
    if not html:
        print("[ERROR CRÍTICO] No se pudo descargar la agenda.")
        sys.exit(1)
        
    dial_map = load_dial_mapping()
    stream_map = load_ezdakit_streams_for_agenda()
    
    soup = BeautifulSoup(html, 'html.parser')
    days = soup.find_all('div', class_='events-day')
    
    if not days:
        print("[ERROR CRÍTICO] No se encontraron eventos en el HTML.")
        sys.exit(1)
        
    entries = []
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    
    for day_div in days:
        date_iso = day_div.get('data-date')
        if not date_iso: continue
        try:
            dt = datetime.datetime.strptime(date_iso, "%Y-%m-%d")
            dia_str = f"{dt.strftime('%d-%m')} ({dias_semana[dt.weekday()]})"
        except: continue
        
        rows = day_div.find_all('tr', class_='event-row')
        for row in rows:
            event_name = row.get('data-event-id')
            comp = row.find('div', class_='competition-info')
            competition = comp.get_text(strip=True) if comp else ""
            
            tds = row.find_all('td')
            if len(tds) >= 3:
                if not event_name or event_name.endswith("--"):
                    time_val = tds[0].get_text(strip=True)
                    teams = tds[2].get_text(strip=True)
                    event_name = f"{time_val}-{teams}"
                if not competition:
                    competition = tds[1].get_text(strip=True)

            processed_ids = set()
            channels = row.find_all('span', class_='channel-link')
            
            for ch in channels:
                txt = ch.get_text()
                match = re.search(r'\((?:M)?(\d+).*?\)', txt)
                if match:
                    dial = match.group(1)
                    tvgid = dial_map.get(dial)
                    
                    if tvgid and tvgid in stream_map:
                        for st in stream_map[tvgid]:
                            aid = st['id']
                            qual = st['quality']
                            
                            if aid in blacklist_map: continue
                            if aid in processed_ids: continue
                            processed_ids.add(aid)
                            
                            prefix = aid[:3]
                            final_name = f"{event_name} ({tvgid}){qual} ({prefix})"
                            group_title = f"{dia_str} {competition}".strip()
                            
                            entry = f'#EXTINF:-1 group-title="{group_title}" tvg-name="{final_name}",{final_name}\nhttp://127.0.0.1:6878/ace/getstream?id={aid}'
                            entries.append(entry)

    if entries:
        full_content = HEADER_M3U + "\n".join(entries)
        Path(FILE_EVENTOS).write_text(full_content, encoding='utf-8')
        print(f"[ÉXITO] Generado {FILE_EVENTOS} con {len(entries)} eventos.")
        
        Path(DIR_HISTORY).mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        history_name = f"ezdakit_eventos{SUFFIX}_{ts}.m3u"
        Path(f"{DIR_HISTORY}/{history_name}").write_text(full_content, encoding='utf-8')
        
        files = sorted(glob.glob(f"{DIR_HISTORY}/ezdakit_eventos{SUFFIX}_*.m3u"))
        while len(files) > 50:
            os.remove(files[0])
            files.pop(0)
    else:
        print("[ALERTA] No se generaron entradas de eventos.")
        sys.exit(1)

def main():
    Path(DIR_CANALES).mkdir(exist_ok=True)
    dl1 = download_file(URLS_ELCANO, FILE_ELCANO)
    dl2 = download_file(URLS_NEW_ERA, FILE_NEW_ERA)
    
    if not dl1 and not dl2:
        print("[ERROR FATAL] No se pudo descargar ninguna lista. Abortando.")
        sys.exit(1)
        
    blacklist = load_blacklist()
    generate_ezdakit(blacklist)
    generate_csv(blacklist)
    scrape_agenda(blacklist)

if __name__ == "__main__":
    main()
