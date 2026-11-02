import os
import sys
import re
import csv
import json
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
print(f"### VERSIÓN DEL SCRIPT: 2.5 (Robust Playwright & Cloudscraper Fallback)")
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
FILE_ELCANO = get_path("elcano.json")
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
IPNS_HASH = "k2k4r8lm8tkmuxbc8lkmq1in3v0oya1p6pe9o5bu0hu30br5ko08k2gb"

URLS_ELCANO = [
    "https://tokyo.elcano-ipfs.workers.dev/k51qzi5uqu5dh5qej4b9wlcr5i6vhc7rcfkekhrxqek5c9lk6gdaiik820fecs/hashes.json",
    "https://ipfs.io/ipns/k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr/hashes.json",
    "https://gateway.pinata.cloud/ipns/k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr/hashes.json",
    "https://k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr.ipns.dweb.link/hashes.json",
    "https://cloudflare-ipfs.com/ipns/k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr/hashes.json"
]

URLS_AGENDA = [
    "https://kiroideuno.pages.gay/"
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

def clean_channel_name(name, ace_id_suffix):
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
    
    cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    
    kept_lines = []
    for line in existing_lines:
        match = re.match(r'^\[(\d{4}-\d{2}-\d{2})', line)
        if match:
            try:
                line_date = datetime.datetime.strptime(match.group(1), "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
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

def load_channel_maps():
    print(f"[2] Cargando Mapas de Canales ({FILE_DIAL_MAP})...")
    dial_map = {} 
    name_map = {}
    
    path = Path(FILE_DIAL_MAP)
    if not path.exists():
        print(f"    [ERROR] No existe {FILE_DIAL_MAP}. El scraping fallará.")
        return dial_map, name_map
        
    content = read_file_safe(path)
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        dial = row.get('Dial_Movistar(M)', '').strip()
        tvg = row.get('TV_guide_id', '').strip()
        name = row.get('Canal', '').strip()
        
        if dial and tvg:
            dial_map[dial] = {'tvg': tvg, 'name': name}
        
        if name and tvg:
            name_map[name.upper()] = tvg
            
    print(f"    -> {len(dial_map)} diales y {len(name_map)} nombres mapeados.")
    return dial_map, name_map

# ============================================================================================
# PROCESAMIENTO DE LISTAS (ELCANO JSON + FORZADOS)
# ============================================================================================

def fetch_elcano_json(urls, output_filename):
    print(f"   -> Descargando fuente Elcano JSON ({output_filename})...")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    
    for url in urls:
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                try:
                    data_json = r.json()
                    if "hashes" in data_json or isinstance(data_json, list):
                        Path(output_filename).write_text(r.text, encoding='utf-8')
                        print(f"      [OK] Fuente JSON obtenida desde: {url[:60]}...")
                        return data_json
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
    print(f"      [ERROR] No se pudo descargar Elcano JSON desde ninguna URL.")
    return None

def parse_elcano_data(json_data, source_tag="E"):
    data = {}
    if not json_data:
        return data
    
    items = json_data.get("hashes", []) if isinstance(json_data, dict) else json_data
    
    for item in items:
        if not isinstance(item, dict): continue
        aid = item.get("hash", "").strip()
        if not aid or len(aid) != 40: continue
        
        raw_name = item.get("title", "").strip()
        tvg_id = item.get("tvg_id", "").strip() or "Unknown"
        group = item.get("group", "").strip()
        url = f"acestream://{aid}"
        
        data[aid] = {
            'name': raw_name,
            'tvg': tvg_id,
            'group': group,
            'url': url,
            'source': source_tag
        }
    return data

def build_master_channel_list(blacklist):
    print(f"[3] Procesando y construyendo lista maestra de canales (Elcano JSON + Forzados)...")
    
    elcano_json_data = fetch_elcano_json(URLS_ELCANO, FILE_ELCANO)
    elcano = parse_elcano_data(elcano_json_data, "E")
    forced_channels = load_forced_channels()
    
    all_ids = set(elcano.keys()) | set(forced_channels.keys())
    if not all_ids:
        print("[ERROR CRÍTICO] No se pudo obtener ninguna lista de canales desde Elcano JSON.")
        sys.exit(1)
        
    master_db = []

    for aid in all_ids:
        e_data = elcano.get(aid, {})
        f_data = forced_channels.get(aid, None)
        
        name_e = e_data.get('name', '')
        group_e = e_data.get('group', '')
        tvg_e = e_data.get('tvg', '')

        nombre_supuesto = clean_channel_name(name_e, aid[-4:])
        if not nombre_supuesto: nombre_supuesto = "DESCONOCIDO"
        
        quality_tag = determine_quality(name_e)
        clean_quality = quality_tag.strip().replace("(", "").replace(")", "")
        
        final_source = "E"
        final_url = e_data.get('url')
        if not final_url: final_url = f"acestream://{aid}"
        
        final_group = group_e if group_e else "OTROS"
        final_tvg = tvg_e if (tvg_e and tvg_e != "Unknown") else "Unknown"

        if f_data:
            nombre_supuesto = f_data['name']
            final_group = f_data['group']
            final_tvg = f_data['tvg']
            clean_quality = f_data['quality']
            quality_tag = f" ({clean_quality})" if clean_quality else ""
            final_source = "F"

        in_bl = "yes" if aid in blacklist else "no"
        bl_real_name = blacklist.get(aid, "")

        master_db.append({
            'ace_id': aid,
            'nombre_e': name_e,
            'nombre_ne': '',
            'tvg_e': tvg_e,
            'tvg_ne': '',
            'grupo_e': group_e,
            'grupo_ne': '',
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
    
    master_db.sort(key=lambda x: (x['final_group'] or "ZZZ", x['nombre_supuesto']))
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
        grp = item['final_group'] if item['final_group'] else "OTROS"
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
# SCRAPING Y EVENTOS (CLOUDSCRAPER + PLAYWRIGHT FALLBACK)
# ============================================================================================

def get_fresh_agenda_html():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    print(f"    [FETCH AGENDA] UTC: {now_utc.strftime('%Y-%m-%d %H:%M')}.")
    
    target_url = "https://kiroideuno.pages.gay/"
    elcano_json_url = URLS_ELCANO[0]

    # INTENTO 1: Directo con Cloudscraper
    print(f"    -> [Intento 1] Solicitud HTTP directa a {target_url}...")
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        r = scraper.get(target_url, timeout=25)
        if r.status_code == 200:
            r.encoding = 'utf-8'
            html = r.text
            if "event-row" in html or "events-day" in html or "<tr" in html:
                print("      [OK] HTML obtenido directamente vía Cloudscraper.")
                return html
            else:
                print("      [AVISO] Petición HTTP directa exitosa pero requiere renderizado de JavaScript.")
    except Exception as e:
        print(f"      [AVISO] Cloudscraper no pudo obtener la página: {str(e)[:60]}...")

    # INTENTO 2: Playwright Headless Browser (Robusto con wait_until='commit')
    print(f"    -> [Intento 2] Iniciando Playwright Headless Browser...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
            )
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800}
            )
            
            # Inyectar la URL del JSON de Elcano en el localStorage de la sesión
            context.add_init_script(f"""
                try {{
                    localStorage.setItem('sources', '{elcano_json_url}');
                    localStorage.setItem('acestream_sources', '{elcano_json_url}');
                }} catch(e) {{}}
            """)
            
            page = context.new_page()
            print(f"    Navegando a {target_url}...")
            
            # Usar wait_until='commit' para evitar bloqueos/hangs en Cloudflare Pages
            response = page.goto(target_url, wait_until='commit', timeout=30000)
            
            # Esperar a que aparezca la estructura del DOM de eventos
            try:
                page.wait_for_selector('table, tr, .events-day, div', timeout=15000)
            except:
                pass
                
            time.sleep(3) # Tiempo adicional para renderizado JS
            
            html_content = page.content()
            browser.close()
            
            if html_content and len(html_content) > 500:
                print("      [OK] HTML capturado con éxito vía Playwright.")
                return html_content
    except Exception as e:
        print(f"      [ERROR Playwright] {str(e)}")

    return None

def scrape_and_match(dial_map, name_map, master_db):
    print(f"[6] Scraping de Agenda (3 días) y cruce de datos...")
    
    tvg_index = {}
    for item in master_db:
        if item['final_tvg'] and item['final_tvg'] != "Unknown":
            if item['final_tvg'] not in tvg_index: tvg_index[item['final_tvg']] = []
            tvg_index[item['final_tvg']].append(item)
            
    html = get_fresh_agenda_html()
            
    if not html:
        print("    [ERROR] No se pudo obtener el HTML de la agenda.")
        return [], []

    soup = BeautifulSoup(html, 'html.parser')
    
    # Buscar bloques de días
    days = soup.find_all('div', class_='events-day')
    if not days:
        # Fallback: Buscar tablas si no están envueltas en divs
        days = soup.find_all('table')
        
    if not days:
        print("    [ERROR] HTML sin bloques ni tablas de eventos.")
        return [], []

    events_list = []
    discarded_list = [] 
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

    for day_div in days:
        date_iso = day_div.get('data-date')
        if not date_iso:
            # Si no hay data-date, usar la fecha actual
            date_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        
        try:
            dt = datetime.datetime.strptime(date_iso, "%Y-%m-%d")
            fecha_csv = date_iso
            dia_m3u = f"{dt.strftime('%m-%d')} ({dias_semana[dt.weekday()]})"
        except: continue

        rows = day_div.find_all('tr')
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
            
            channels = row.find_all(['span', 'td', 'a'], class_=re.compile(r'channel|link|stream', re.I))
            if not channels and len(tds) >= 4:
                channels = [tds[3]]

            processed_ace_ids = set()
            
            for ch in channels:
                txt = ch.get_text().strip()
                if not txt or "VER PARTIDO" in txt.upper() and len(txt) < 15:
                    continue
                    
                canal_agenda_real = txt
                dial = None
                canal_agenda_clean = txt
                
                m_match = re.search(r'(\([^)]*?M(\d+)[^)]*?\))', txt)
                d_match = re.search(r'(\((\d+)\))', txt)

                if m_match:
                    dial = m_match.group(2)
                    canal_agenda_clean = txt.replace(m_match.group(1), "")
                elif d_match:
                    if "ORANGE" not in txt.upper():
                        dial = d_match.group(2)
                        canal_agenda_clean = txt.replace(d_match.group(1), "")
                    else:
                        canal_agenda_clean = txt
                
                canal_agenda_clean = canal_agenda_clean.upper().strip()
                
                # Reglas de normalización
                canal_agenda_clean = canal_agenda_clean.replace("ELLAS VAMOS", "MOVISTAR ELLAS")
                canal_agenda_clean = canal_agenda_clean.replace("M+ DEPORTES", "MOVISTAR DEPORTES")
                canal_agenda_clean = canal_agenda_clean.replace("LALIGA TV HYPERMOTION", "HYPERMOTION")
                canal_agenda_clean = canal_agenda_clean.replace("DAZN LALIGA", "DAZN LA LIGA")
                canal_agenda_clean = re.sub(r'\s*:\s*VER PARTIDO\s*', '', canal_agenda_clean)
                canal_agenda_clean = canal_agenda_clean.replace("PLUS+", "PLUS")
                canal_agenda_clean = re.sub(r'^M\+\s*', '', canal_agenda_clean)
                canal_agenda_clean = canal_agenda_clean.replace("LALIGA", "M+ LALIGA")
                canal_agenda_clean = canal_agenda_clean.strip()
                
                if canal_agenda_clean == "DAZN LA LIGA":
                    canal_agenda_clean = "DAZN LA LIGA 1"

                target_tvg = name_map.get(canal_agenda_clean)

                if not target_tvg:
                    discarded_list.append({
                        'dial_M': dial or '?',
                        'nombre_canal_descartado': txt,
                        'evento_descartado': event_raw or 'Unknown',
                        'motivo': f'mapping_not_found_for: {canal_agenda_clean}'
                    })
                    continue
                
                nombre_canal_csv = canal_agenda_clean 
                available_streams = tvg_index.get(target_tvg, [])
                
                if not available_streams:
                    discarded_list.append({
                        'dial_M': dial or '?',
                        'nombre_canal_descartado': txt,
                        'evento_descartado': event_raw or 'Unknown',
                        'motivo': 'no_streams'
                    })
                    continue
                    
                for stream in available_streams:
                    aid = stream['ace_id']
                    if aid in processed_ace_ids: continue
                    processed_ace_ids.add(aid)
                    
                    events_list.append({
                        'acestream_id': aid,
                        'dial_M': dial or '?',
                        'tvg_id': target_tvg,
                        'fecha': fecha_csv,
                        'hora': hora_evento,
                        'evento': event_raw or 'Evento Deportivo',
                        'competicion': competition,
                        'nombre_canal': nombre_canal_csv,
                        'canal_agenda': canal_agenda_clean, 
                        'canal_agenda_real': canal_agenda_real,
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
        fields = ['acestream_id', 'dial_M', 'tvg_id', 'fecha', 'hora', 'evento', 
                  'competición', 'nombre_canal', 'canal_agenda', 'canal_agenda_real', 'calidad', 'lista_negra']
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
                'canal_agenda_real': ev['canal_agenda_real'],
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
    dial_map, name_map = load_channel_maps()
    
    master_db = build_master_channel_list(blacklist)
    
    generate_correspondencias(master_db)
    generate_ezdakit_m3u(master_db)
    
    events_list, discarded_list = scrape_and_match(dial_map, name_map, master_db)
    
    generate_eventos_files(events_list)
    generate_descartes_csv(discarded_list)

    print("\n######################################################################")
    print("### PROCESO COMPLETADO")
    print("######################################################################")

if __name__ == "__main__":
    main()
