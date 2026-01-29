# ============================================================================================
# SCRIPT DE ACTUALIZACIÓN DE CANALES Y AGENDA DEPORTIVA
#
# VERSIÓN: 1.6
#
# CHANGELOG:
# - [v1.6] Añadida regla exacta: "DAZN LA LIGA" >> "DAZN LA LIGA 1" (Solo si coincide exacto).
# - [v1.5] Añadida regla de normalización final: "LALIGA" >> "M+ LALIGA".
# - [v1.4] Refuerzo de limpieza con Regex para 'canal_agenda'. Logs de debug añadidos.
# - [v1.3] Reglas de normalización específicas (ELLAS VAMOS, M+, etc.).
# - [v1.2] Añadida columna 'canal_agenda' limpia.
# - [v1.1] Forzado de mayúsculas global en 'clean_channel_name'.
# ============================================================================================

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
print(f"### VERSIÓN DEL SCRIPT: 1.6")
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
FILE_DESCARTES = get_path(f"{DIR_CANALES}/descartes.csv")
FILE_PROXIES_LOG = f"{DIR_DEBUG}/proxies.log"

# Ficheros de ENTRADA
FILE_BLACKLIST = get_path(f"{DIR_CANALES}/lista_negra.csv") 
FILE_DIAL_MAP = get_path(f"{DIR_CANALES}/listado_canales.csv")
FILE_FORZADOS = get_path(f"{DIR_CANALES}/canales_forzados.csv")

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

# URLs Agenda (Limpias)
URLS_AGENDA = [
    f"https://ipfs.io/ipns/{IPNS_HASH}/",
    f"https://cloudflare-ipfs.com/ipns/{IPNS_HASH}/",
    f"https://w3s.link/ipns/{IPNS_HASH}/",
    f"https://{IPNS_HASH}.ipns.dweb.link/",
    f"https://dweb.link/ipns/{IPNS_HASH}/",
    f"https://gateway.pinata.cloud/ipns/{IPNS_HASH}/"
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
            r = session.get(url, timeout=60)
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
    """
    Limpieza básica del nombre del canal para generar el nombre_supuesto.
    [v1.1] FUERZA MAYÚSCULAS AL FINAL.
    """
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
    
    # CAMBIO v1.1: Devolver siempre mayúsculas
    return name.upper()

def determine_quality(name):
    u = name.upper()
    if "4K" in u or "UHD" in u: return " (UHD)"
    if "1080" in u or "FHD" in u: return " (FHD)"
    return " (HD)"

# ============================================================================================
# LOGICA DE LOG DE PROXIES
# ============================================================================================

def update_proxies_log(new_entries):
    Path(DIR_DEBUG).mkdir(exist_ok=True)
    log_path = Path(FILE_PROXIES_LOG)
    
    existing_lines = []
    if log_path.exists():
        existing_lines = log_path.read_text(encoding='utf-8').splitlines()
    
    cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    
    kept_lines = []
    for line in existing_lines:
        match = re.match(r'^\[(\d{4}-\d{2}-\d{2})', line)
        if match:
            try:
                line_date = datetime.datetime.strptime(match.group(1), "%Y-%m-%d")
                if line_date >= cutoff_date:
                    kept_lines.append(line)
            except:
                kept_lines.append(line)
        else:
            kept_lines.append(line)
            
    final_content = "\n".join(new_entries + kept_lines)
    log_path.write_text(final_content, encoding='utf-8')
    print(f"    [LOG] Proxies log actualizado ({len(new_entries)} nuevas, {len(kept_lines)} mantenidas).")

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

def load_forced_channels():
    print(f"[1.1] Cargando Canales Forzados ({FILE_FORZADOS})...")
    forced = {}
    path = Path(FILE_FORZADOS)
    if not path.exists():
        print(f"    [AVISO] No existe {FILE_FORZADOS}. Se continúa sin canales forzados.")
        return forced
    
    content = read_file_safe(path)
    content = content.replace('\ufeff', '')
    
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        aid = row.get('acestream_id', '').strip()
        if aid:
            forced[aid] = {
                'tvg': row.get('tvg-id', '').strip(),
                'name': row.get('nombre_supuesto', '').strip(),
                'group': row.get('grupo', '').strip(),
                'quality': row.get('calidad', '').strip()
            }
    print(f"    -> {len(forced)} canales forzados cargados.")
    return forced

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
# PROCESAMIENTO DE LISTAS (ELCANO / NEW ERA + FORZADOS)
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
    forced_channels = load_forced_channels()
    
    all_ids = set(elcano.keys()) | set(newera.keys()) | set(forced_channels.keys())
    master_db = []
    
    new_era_names_map = {v['name']: v['tvg'] for v in newera.values() if v['tvg'] != "Unknown"}

    for aid in all_ids:
        e_data = elcano.get(aid, {})
        n_data = newera.get(aid, {})
        f_data = forced_channels.get(aid, None)
        
        name_ne = n_data.get('name', '')
        group_ne = n_data.get('group', '')
        tvg_ne = n_data.get('tvg', '')
        
        name_e = e_data.get('name', '')
        group_e = e_data.get('group', '')
        tvg_e = e_data.get('tvg', '')
        
        if not tvg_e or tvg_e == "Unknown":
            if name_e in new_era_names_map:
                tvg_e = new_era_names_map[name_e]

        raw_name_for_clean = name_ne if name_ne else name_e
        
        # [v1.1] clean_channel_name ahora devuelve MAYUSCULAS
        nombre_supuesto = clean_channel_name(raw_name_for_clean, aid[-4:])
        if not nombre_supuesto: nombre_supuesto = "DESCONOCIDO"
        
        quality_tag = determine_quality((name_ne + " " + name_e))
        clean_quality = quality_tag.strip().replace("(", "").replace(")", "")
        
        final_source = "N" if aid in newera else "E"
        final_url = n_data.get('url') if aid in newera else e_data.get('url')
        
        final_group = group_ne if group_ne else group_e
        if not final_group: final_group = "OTROS"
        
        final_tvg = tvg_ne if (tvg_ne and tvg_ne != "Unknown") else tvg_e
        if not final_tvg: final_tvg = "Unknown"

        if f_data:
            nombre_supuesto = f_data['name']
            final_group = f_data['group']
            final_tvg = f_data['tvg']
            clean_quality = f_data['quality']
            quality_tag = f" ({clean_quality})" if clean_quality else ""
            final_source = "F"
            if not final_url: final_url = f"acestream://{aid}"

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

def get_fresh_agenda_html():
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    
    now_utc = datetime.datetime.utcnow()
    today_date = now_utc.date()
    
    print(f"    [SMART FETCH] Hora UTC: {now_utc.strftime('%H:%M')}.")
    
    log_entries = []
    last_working_html = None
    fresh_html = None
    
    for url in URLS_AGENDA:
        try:
            print(f"    Probando: {url} ...")
            
            r = scraper.get(url, timeout=60)
            if r.status_code == 200:
                r.encoding = 'utf-8'
                html_content = r.text
                
                soup_temp = BeautifulSoup(html_content, 'html.parser')
                first_day_div = soup_temp.find('div', class_='events-day')
                
                status_msg = "OK"
                is_actually_fresh = False
                
                if first_day_div:
                    date_str = first_day_div.get('data-date')
                    try:
                        content_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        if content_date >= today_date:
                            status_msg = f"FRESH (Data from {date_str})"
                            is_actually_fresh = True
                        else:
                            status_msg = f"STALE (Data from {date_str})"
                            is_actually_fresh = False
                    except:
                        status_msg = "WARN (Date parsing failed)"
                else:
                    status_msg = "WARN (No events found)"

                timestamp = now_utc.strftime('%Y-%m-%d %H:%M')
                log_entries.append(f"[{timestamp}] {url} | {status_msg}")
                
                last_working_html = html_content
                
                if is_actually_fresh:
                    fresh_html = html_content
                    print(f"      -> {status_msg}. USANDO ESTE PROXY.")
                    log_entries[-1] += " [SELECTED]"
                    break 
                else:
                    print(f"      -> {status_msg}. Buscando siguiente mejor opción...")

        except Exception as e:
            err_str = str(e).split('(')[0] if '(' in str(e) else str(e)
            print(f"      -> ERROR: {err_str}...")
            log_entries.append(f"[{now_utc.strftime('%Y-%m-%d %H:%M')}] {url} | ERROR: {err_str}")

    update_proxies_log(log_entries)

    if fresh_html:
        return fresh_html
    elif last_working_html:
        print("    [AVISO] No se encontraron proxies actualizados. Usando el último funcional.")
        return last_working_html
    else:
        print("    [ERROR] Ningún proxy respondió correctamente.")
        return None

def scrape_and_match(dial_map, master_db):
    print(f"[6] Scraping de Agenda y cruce de datos...")
    
    # Índice de AceStreams por TVG para búsqueda rápida
    tvg_index = {}
    for item in master_db:
        if item['final_tvg'] and item['final_tvg'] != "Unknown":
            if item['final_tvg'] not in tvg_index: tvg_index[item['final_tvg']] = []
            tvg_index[item['final_tvg']].append(item)
            
    html = get_fresh_agenda_html()
            
    if not html:
        return [], []

    soup = BeautifulSoup(html, 'html.parser')
    days = soup.find_all('div', class_='events-day')
    if not days:
        print("    [ERROR] HTML sin eventos. Estructura web ha cambiado.")
        return [], []

    events_list = []
    discarded_list = [] 
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

    for day_div in days:
        date_iso = day_div.get('data-date')
        if not date_iso: continue
        
        try:
            dt = datetime.datetime.strptime(date_iso, "%Y-%m-%d")
            fecha_csv = date_iso
            dia_m3u = f"{dt.strftime('%m-%d')} ({dias_semana[dt.weekday()]})"
        except: continue

        rows = day_div.find_all('tr', class_='event-row')
        for row in rows:
            event_raw = row.get('data-event-id')
            comp_div = row.find('div', class_='competition-info')
            competition = comp_div.get_text(separator=' ', strip=True) if comp_div else ""
            
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
                txt = ch.get_text().strip()
                
                # --- [v1.6] EXTRACCIÓN Y NORMALIZACIÓN DE CANAL AGENDA ---
                dial = None
                canal_agenda_clean = txt # Valor inicial
                
                m_match = re.search(r'(\([^)]*?M(\d+)[^)]*?\))', txt)
                d_match = re.search(r'(\((\d+)\))', txt)

                # 1. Extracción del Dial y Limpieza base
                if m_match:
                    dial = m_match.group(2)
                    canal_agenda_clean = txt.replace(m_match.group(1), "")
                elif d_match:
                    if "ORANGE" not in txt.upper():
                        dial = d_match.group(2)
                        canal_agenda_clean = txt.replace(d_match.group(1), "")
                    else:
                        canal_agenda_clean = txt # Es Orange
                
                # 2. Normalización Estricta [v1.4 - REGEX]
                canal_agenda_clean = canal_agenda_clean.upper().strip()
                
                # Reglas secuenciales robustas:
                # Regla 1: ELLAS VAMOS
                canal_agenda_clean = canal_agenda_clean.replace("ELLAS VAMOS", "MOVISTAR ELLAS")
                # Regla 2: M+ DEPORTES
                canal_agenda_clean = canal_agenda_clean.replace("M+ DEPORTES", "MOVISTAR DEPORTES")
                # Regla 3: HYPERMOTION
                canal_agenda_clean = canal_agenda_clean.replace("LALIGA TV HYPERMOTION", "HYPERMOTION")
                # Regla 4: DAZN LALIGA (Sin tocar número)
                canal_agenda_clean = canal_agenda_clean.replace("DAZN LALIGA", "DAZN LA LIGA")
                
                # Regla 5: Eliminar " : VER PARTIDO"
                canal_agenda_clean = re.sub(r'\s*:\s*VER PARTIDO\s*', '', canal_agenda_clean)
                
                # Regla 6: PLUS+
                canal_agenda_clean = canal_agenda_clean.replace("PLUS+", "PLUS")
                
                # Regla 7: Eliminar "M+ " al principio
                canal_agenda_clean = re.sub(r'^M\+\s*', '', canal_agenda_clean)
                
                # [v1.5] Regla 8: "LALIGA" >> "M+ LALIGA"
                canal_agenda_clean = canal_agenda_clean.replace("LALIGA", "M+ LALIGA")
                
                canal_agenda_clean = canal_agenda_clean.strip()
                
                # [v1.6] Regla 9: DAZN LA LIGA >> DAZN LA LIGA 1 (Exacto)
                if canal_agenda_clean == "DAZN LA LIGA":
                    canal_agenda_clean = "DAZN LA LIGA 1"
                # ---------------------------------------------------------

                if dial:
                    map_info = dial_map.get(dial)
                    if not map_info:
                        discarded_list.append({
                            'dial_M': dial,
                            'nombre_canal_descartado': txt,
                            'evento_descartado': event_raw,
                            'motivo': 'unlisted'
                        })
                        continue
                    
                    tvgid = map_info['tvg']
                    nombre_canal_csv = map_info['name'] 
                    
                    available_streams = tvg_index.get(tvgid, [])
                    if not available_streams:
                        discarded_list.append({
                            'dial_M': dial,
                            'nombre_canal_descartado': txt,
                            'evento_descartado': event_raw,
                            'motivo': 'no_streams'
                        })
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
                            'canal_agenda': canal_agenda_clean, # Columna normalizada
                            'calidad': stream['calidad_clean'],
                            'lista_negra': stream['in_blacklist'],
                            'calidad_tag': stream['calidad_tag'],
                            'dia_str_m3u': dia_m3u,
                            'ace_prefix': aid[:3]
                        })

    print(f"    -> Encontrados {len(events_list)} combinaciones evento-canal.")
    print(f"    -> Descartados {len(discarded_list)} intentos.")
    return events_list, discarded_list

def generate_descartes_csv(discarded_list):
    print(f"[8] Generando {FILE_DESCARTES}...")
    Path(DIR_CANALES).mkdir(exist_ok=True)
    with open(FILE_DESCARTES, 'w', newline='', encoding='utf-8-sig') as f:
        fields = ['dial_M', 'nombre_canal_descartado', 'evento_descartado', 'motivo']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for d in discarded_list:
            w.writerow({
                'dial_M': d['dial_M'],
                'nombre_canal_descartado': d['nombre_canal_descartado'],
                'evento_descartado': d['evento_descartado'],
                'motivo': d['motivo']
            })
    print(f"    -> Generado CSV de descartes con {len(discarded_list)} registros.")

def generate_eventos_files(events_list):
    print(f"[7] Generando ficheros de eventos...")
    events_list.sort(key=lambda x: (x['fecha'], x['hora'], x['competicion'], x['evento']))
    
    Path(DIR_CANALES).mkdir(exist_ok=True)
    with open(FILE_EVENTOS_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        # [v1.2] Añadida columna canal_agenda
        fields = ['acestream_id', 'dial_M', 'tvg_id', 'fecha', 'hora', 'evento', 
                  'competición', 'nombre_canal', 'canal_agenda', 'calidad', 'lista_negra']
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
                'canal_agenda': ev['canal_agenda'],
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
    
    # Desempaquetamos los dos resultados: eventos validos y descartes
    events_list, discarded_list = scrape_and_match(dial_map, master_db)
    
    generate_eventos_files(events_list)
    generate_descartes_csv(discarded_list)

    print("\n######################################################################")
    print("### PROCESO COMPLETADO")
    print("######################################################################")

if __name__ == "__main__":
    main()
