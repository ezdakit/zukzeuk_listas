import os
import sys
import re
import csv
import time
import datetime
import requests
import cloudscraper
from bs4 import BeautifulSoup
from pathlib import Path
import io

# ============================================================================================
# CONFIGURACIÓN Y MODO TESTING
# ============================================================================================

TEST_MODE = "--testing" in sys.argv
SUFFIX = "_testing" if TEST_MODE else ""

print(f"######################################################################")
print(f"### INICIANDO SISTEMA DE ACTUALIZACIÓN {'(MODO TESTING)' if TEST_MODE else '(PRODUCCIÓN)'}")
print(f"### Sufijo de archivos de salida: '{SUFFIX}'")
print(f"######################################################################\n")

# Carpetas
DIR_CANALES = "canales"
DIR_DEBUG = ".debug"

# Función para gestionar nombres de archivo con sufijo
def get_path(filename):
    base, ext = os.path.splitext(filename)
    if "/" in base:
        folder, name = base.rsplit("/", 1)
        return f"{folder}/{name}{SUFFIX}{ext}"
    return f"{base}{SUFFIX}{ext}"

# Ficheros de SALIDA (Llevan sufijo en testing)
FILE_ELCANO = get_path("elcano.m3u")
FILE_NEW_ERA = get_path("new_era.m3u")
FILE_EZDAKIT = get_path("ezdakit.m3u")
FILE_CORRESPONDENCIAS = get_path(f"{DIR_CANALES}/correspondencias.csv")
FILE_EVENTOS_CSV = get_path(f"{DIR_CANALES}/eventos_canales.csv")
FILE_EVENTOS_M3U = get_path("ezdakit_eventos.m3u")

# Ficheros de ENTRADA (Estricto: Si es testing busca _testing.csv)
FILE_BLACKLIST = get_path(f"{DIR_CANALES}/lista_negra.csv") 
FILE_DIAL_MAP = get_path(f"{DIR_CANALES}/listado_canales.csv")

# URLs
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

# ============================================================================================
# UTILIDADES GENÉRICAS
# ============================================================================================

def read_file_safe(path_obj):
    if not path_obj.exists(): return ""
    raw = path_obj.read_bytes()
    try:
        content = raw.decode('utf-8')
        if "Ã" in content: raise ValueError()
        return content
    except:
        return raw.decode('latin-1', errors='ignore')

def download_file(urls, output_filename):
    print(f"   -> Descargando {output_filename}...")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    
    for url in urls:
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                if "#EXTM3U" in r.text[:200]:
                    Path(output_filename).write_text(r.text, encoding='utf-8')
                    print(f"      [OK] Fuente: {url[:40]}...")
                    return True
        except:
            pass
    print(f"      [ERROR] No se pudo descargar {output_filename}")
    return False

def clean_channel_name(name, ace_id_suffix):
    """Lógica de limpieza para generar el nombre_supuesto"""
    if not name: return ""
    name = re.sub(r'-->.*', '', name)
    
    terms = [
        r'1080p', r'720p', r'FHD', r'UHD', r'4K', r'8K', 
        r'HD', r'SD',
        r'50fps', r'HEVC', r'AAC', r'H\.265',
        r'\(ES\)', r'\(SP\)', r'\(RU\)', r'\(M\d+\)', r'\(O\d+\)', 
        r'\(BACKUP\)', r'\|', r'vip', r'premium', r'\( original \)',
        r'\bBAR\b'
    ]
    for term in terms:
        name = re.sub(term, '', name, flags=re.IGNORECASE)
    
    name = name.replace('  ', ' ').strip().rstrip(' -_')
    
    if ace_id_suffix and name.endswith(ace_id_suffix):
        name = name[:-4].strip()
    name = re.sub(r'\s+[0-9a-fA-F]{4}$', '', name)
    
    return name

def determine_quality(name):
    u = name.upper()
    if "4K" in u or "UHD" in u: return " (UHD)"
    if "1080" in u or "FHD" in u: return " (FHD)"
    return " (HD)"

# ============================================================================================
# CARGA DE DATOS ESTÁTICOS
# ============================================================================================

def load_blacklist():
    print(f"[1] Cargando Lista Negra ({FILE_BLACKLIST})...")
    bl = {}
    path = Path(FILE_BLACKLIST)
    if not path.exists():
        print(f"    [AVISO] No existe {FILE_BLACKLIST}. Se continúa sin filtro.")
        return bl
    
    content = read_file_safe(path)
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        aid = row.get('ace_id', '').strip()
        real = row.get('canal_real', '').strip()
        if aid:
            bl[aid] = real
    print(f"    -> {len(bl)} IDs en lista negra.")
    return bl

def load_dial_mapping():
    print(f"[2] Cargando Mapeo de Diales ({FILE_DIAL_MAP})...")
    mapping = {} 
    path = Path(FILE_DIAL_MAP)
    if not path.exists():
        print(f"    [ERROR] No existe {FILE_DIAL_MAP}. El scraping fallará.")
        return mapping
        
    content = read_file_safe(path)
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        dial = row.get('Dial_Movistar(M)', '').strip()
        tvg = row.get('TV_guide_id', '').strip()
        name = row.get('Canal', '').strip()
        
        if dial and tvg:
            mapping[dial] = {'tvg': tvg, 'name': name}
            
    print(f"    -> {len(mapping)} diales mapeados.")
    return mapping

# ============================================================================================
# PROCESAMIENTO DE LISTAS (ELCANO / NEW ERA)
# ============================================================================================

def parse_m3u(file_path, source_tag):
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
                        'group': mg.group(1).strip() if mg else "",
                        'url': url,
                        'source': source_tag
                    }
        i += 1
    return data

def build_master_channel_list(blacklist):
    print(f"[3] Procesando y fusionando listas M3U...")
    
    if not download_file(URLS_ELCANO, FILE_ELCANO) and not download_file(URLS_NEW_ERA, FILE_NEW_ERA):
        print("[ERROR CRÍTICO] No se pudo descargar ninguna lista.")
        sys.exit(1)

    elcano = parse_m3u(FILE_ELCANO, "E")
    newera = parse_m3u(FILE_NEW_ERA, "N")
    
    all_ids = set(elcano.keys()) | set(newera.keys())
    master_db = []
    
    new_era_names_map = {v['name']: v['tvg'] for v in newera.values() if v['tvg'] != "Unknown"}

    for aid in all_ids:
        e_data = elcano.get(aid, {})
        n_data = newera.get(aid, {})
        
        name_ne = n_data.get('name', '')
        group_ne = n_data.get('group', '')
        tvg_ne = n_data.get('tvg', '')
        
        name_e = e_data.get('name', '')
        group_e = e_data.get('group', '')
        tvg_e = e_data.get('tvg', '')
        
        if not tvg_e or tvg_e == "Unknown":
            if name_e in new_era_names_map:
                tvg_e = new_era_names_map[name_e]

        # Nombre para limpieza (Prioridad New Era)
        raw_name_for_clean = name_ne if name_ne else name_e
        
        # Limpieza estándar (sin forzar nombre oficial)
        nombre_supuesto = clean_channel_name(raw_name_for_clean, aid[-4:])
        if not nombre_supuesto: nombre_supuesto = "Desconocido"
        
        quality_tag = determine_quality((name_ne + " " + name_e))
        clean_quality = quality_tag.strip().replace("(", "").replace(")", "")
        
        final_source = "N" if aid in newera else "E"
        final_url = n_data.get('url') if aid in newera else e_data.get('url')
        
        final_group = group_ne if group_ne else group_e
        if not final_group: final_group = "OTROS"
        
        final_tvg = tvg_ne if (tvg_ne and tvg_ne != "Unknown") else tvg_e
        if not final_tvg: final_tvg = "Unknown"

        # Gestión Blacklist
        in_bl = "yes" if aid in blacklist else "no"
        bl_real_name = blacklist.get(aid, "")

        master_db.append({
            'ace_id': aid,
            'nombre_e': name_e,
            'nombre_ne': name_ne,
            'tvg_e': tvg_e,
            'tvg_ne': tvg_ne,
            'grupo_e': group_e,
            'grupo_ne': group_ne,
            'nombre_supuesto': nombre_supuesto,
            'calidad_tag': quality_tag,     
            'calidad_clean': clean_quality, 
            'source': final_source,
            'url': final_url,
            'final_group': final_group,
            'final_tvg': final_tvg,
            'in_blacklist': in_bl,
            'blacklist_real_name': bl_real_name
        })
    
    # ORDENACIÓN CENTRALIZADA
    master_db.sort(key=lambda x: (x['grupo_ne'] or "ZZZ", x['nombre_supuesto']))
    
    print(f"    -> Procesados y ordenados {len(master_db)} canales únicos.")
    return master_db

# ============================================================================================
# GENERADORES (CSV, M3U)
# ============================================================================================

def generate_correspondencias(db):
    print(f"[4] Generando {FILE_CORRESPONDENCIAS}...")
    
    Path(DIR_CANALES).mkdir(exist_ok=True)
    with open(FILE_CORRESPONDENCIAS, 'w', newline='', encoding='utf-8-sig') as f:
        fields = ['acestream_id', 'nombre_e', 'nombre_ne', 'tvg-id_e', 'tvg-id_ne', 
                  'nombre_supuesto', 'grupo_e', 'grupo_ne', 'calidad', 'lista_negra', 'canal_real']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        
        for item in db:
            w.writerow({
                'acestream_id': item['ace_id'],
                'nombre_e': item['nombre_e'],
                'nombre_ne': item['nombre_ne'],
                'tvg-id_e': item['tvg_e'],
                'tvg-id_ne': item['tvg_ne'],
                'nombre_supuesto': item['nombre_supuesto'],
                'grupo_e': item['grupo_e'],
                'grupo_ne': item['grupo_ne'],
                'calidad': item['calidad_clean'],
                'lista_negra': item['in_blacklist'],
                'canal_real': item['blacklist_real_name']
            })
    print("    -> Fichero generado correctamente.")

def generate_ezdakit_m3u(db):
    print(f"[5] Generando {FILE_EZDAKIT}...")
    
    entries = []
    for item in db:
        prefix = item['ace_id'][:3]
        # AQUÍ ESTÁ LA CLAVE: Usamos el nombre_supuesto (que viene del limpiado)
        display_name = f"{item['nombre_supuesto']}{item['calidad_tag']} ({item['source']}-{prefix})"
        grp = item['grupo_ne'] if item['grupo_ne'] else "OTROS"
        
        if item['in_blacklist'] == "yes":
            grp = "ZZ_Canales_KO"
            suffix = item['blacklist_real_name'] if item['blacklist_real_name'] else "BLACKLIST"
            display_name += f" >>> {suffix}"

        entry = f'#EXTINF:-1 tvg-id="{item["final_tvg"]}" tvg-name="{display_name}" group-title="{grp}",{display_name}\n{item["url"]}'
        entries.append(entry)
        
    content = HEADER_M3U + "\n" + "\n".join(entries)
    Path(FILE_EZDAKIT).write_text(content, encoding='utf-8')
    print(f"    -> {len(entries)} canales escritos.")

# ============================================================================================
# SCRAPING Y EVENTOS
# ============================================================================================

def scrape_and_match(dial_map, master_db):
    print(f"[6] Scraping de Agenda y cruce de datos...")
    
    tvg_index = {}
    for item in master_db:
        if item['final_tvg'] and item['final_tvg'] != "Unknown":
            if item['final_tvg'] not in tvg_index: tvg_index[item['final_tvg']] = []
            tvg_index[item['final_tvg']].append(item)
            
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    html = None
    for url in URLS_AGENDA:
        try:
            print(f"    Probando {url}...")
            r = scraper.get(url, timeout=60)
            if r.status_code == 200:
                r.encoding = 'utf-8' # Forzar UTF-8
                html = r.text
                break
        except:
            pass
            
    if not html:
        print("    [ERROR] No se pudo descargar la agenda. Se aborta generación de eventos.")
        return []

    # --- DEBUG: GUARDAR HTML CRUDO ---
    try:
        Path(DIR_DEBUG).mkdir(exist_ok=True)
        debug_file = f"{DIR_DEBUG}/agenda_dump{SUFFIX}.html"
        Path(debug_file).write_text(html, encoding='utf-8')
        print(f"    [DEBUG] HTML guardado en {debug_file}")
    except Exception as e:
        print(f"    [AVISO] No se pudo guardar debug HTML: {e}")
    # ---------------------------------

    soup = BeautifulSoup(html, 'html.parser')
    days = soup.find_all('div', class_='events-day')
    if not days:
        print("    [ERROR] HTML sin eventos. Estructura web ha cambiado.")
        return []

    events_list = []
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

    for day_div in days:
        date_iso = day_div.get('data-date') # YYYY-MM-DD
        if not date_iso: continue
        
        try:
            dt = datetime.datetime.strptime(date_iso, "%Y-%m-%d")
            fecha_csv = date_iso
            # MM-DD
            dia_m3u = f"{dt.strftime('%m-%d')} ({dias_semana[dt.weekday()]})"
        except: continue

        rows = day_div.find_all('tr', class_='event-row')
        for row in rows:
            event_raw = row.get('data-event-id')
            comp_div = row.find('div', class_='competition-info')
            competition = comp_div.get_text(strip=True) if comp_div else ""
            
            tds = row.find_all('td')
            hora_evento = "00:00"
            if len(tds) >= 3:
                hora_evento = tds[0].get_text(strip=True)
                if not event_raw or event_raw.endswith("--"):
                    teams = tds[2].get_text(strip=True)
                    event_raw = teams
                if not competition:
                    competition = tds[1].get_text(strip=True)
            
            channels = row.find_all('span', class_='channel-link')
            processed_ace_ids = set()
            
            for ch in channels:
                txt = ch.get_text()
                match = re.search(r'\((?:M)?(\d+).*?\)', txt)
                if match:
                    dial = match.group(1)
                    
                    map_info = dial_map.get(dial)
                    if not map_info:
                        print(f"    [SKIP] Dial {dial} encontrado en web pero NO en listado_canales.csv")
                        continue
                    
                    tvgid = map_info['tvg']
                    nombre_canal_csv = map_info['name'] 
                    
                    available_streams = tvg_index.get(tvgid, [])
                    if not available_streams:
                        print(f"    [SKIP] Dial {dial} ({tvgid}) mapeado, pero SIN STREAMS en listas M3U.")
                        continue
                        
                    for stream in available_streams:
                        aid = stream['ace_id']
                        if aid in processed_ace_ids: continue
                        processed_ace_ids.add(aid)
                        
                        events_list.append({
                            'acestream_id': aid,
                            'dial_M': dial,
                            'tvg_id': tvgid,
                            'fecha': fecha_csv,
                            'hora': hora_evento,
                            'evento': event_raw,
                            'competicion': competition,
                            'nombre_canal': nombre_canal_csv, 
                            'calidad': stream['calidad_clean'],
                            'lista_negra': stream['in_blacklist'],
                            'calidad_tag': stream['calidad_tag'],
                            'dia_str_m3u': dia_m3u,
                            'ace_prefix': aid[:3]
                        })

    print(f"    -> Encontrados {len(events_list)} combinaciones evento-canal.")
    return events_list

def generate_eventos_files(events_list):
    print(f"[7] Generando ficheros de eventos...")
    
    events_list.sort(key=lambda x: (x['fecha'], x['hora'], x['competicion'], x['evento']))
    
    Path(DIR_CANALES).mkdir(exist_ok=True)
    with open(FILE_EVENTOS_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        fields = ['acestream_id', 'dial_M', 'tvg_id', 'fecha', 'hora', 'evento', 
                  'competición', 'nombre_canal', 'calidad', 'lista_negra']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for ev in events_list:
            w.writerow({
                'acestream_id': ev['acestream_id'],
                'dial_M': ev['dial_M'],
                'tvg_id': ev['tvg_id'],
                'fecha': ev['fecha'],
                'hora': ev['hora'],
                'evento': ev['evento'],
                'competición': ev['competicion'],
                'nombre_canal': ev['nombre_canal'],
                'calidad': ev['calidad'],
                'lista_negra': ev['lista_negra']
            })
    print(f"    -> Generado CSV: {FILE_EVENTOS_CSV}")
    
    m3u_entries = []
    
    for ev in events_list:
        if ev['lista_negra'] == "yes": continue
        
        full_event_name = ev['evento']
        if not re.match(r'\d{2}:\d{2}', full_event_name):
             full_event_name = f"{ev['hora']}-{full_event_name}"
        
        final_name = f"{full_event_name} ({ev['nombre_canal']}){ev['calidad_tag']} ({ev['ace_prefix']})"
        group_title = f"{ev['dia_str_m3u']} {ev['competicion']}".strip()
        
        entry = f'#EXTINF:-1 group-title="{group_title}" tvg-name="{final_name}",{final_name}\nhttp://127.0.0.1:6878/ace/getstream?id={ev["acestream_id"]}'
        m3u_entries.append(entry)
        
    if m3u_entries:
        content = HEADER_M3U + "\n" + "\n".join(m3u_entries)
        Path(FILE_EVENTOS_M3U).write_text(content, encoding='utf-8')
        print(f"    -> Generado M3U: {FILE_EVENTOS_M3U} con {len(m3u_entries)} entradas.")
    else:
        print("    [ALERTA] No se generaron entradas M3U.")


# ============================================================================================
# MAIN
# ============================================================================================

def main():
    Path(DIR_CANALES).mkdir(exist_ok=True)
    blacklist = load_blacklist()
    dial_map = load_dial_mapping()
    
    master_db = build_master_channel_list(blacklist)
    
    generate_correspondencias(master_db)
    generate_ezdakit_m3u(master_db)
    
    events_list = scrape_and_match(dial_map, master_db)
    generate_eventos_files(events_list)

    print("\n######################################################################")
    print("### PROCESO COMPLETADO")
    print("######################################################################")

if __name__ == "__main__":
    main()
