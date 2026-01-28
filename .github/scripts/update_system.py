import os
import sys
import re
import csv
import time
import datetime
import requests
import cloudscraper
import sqlite3  # <--- EL MOTOR NUEVO
from bs4 import BeautifulSoup
from pathlib import Path
import io

# ============================================================================================
# CONFIGURACIÓN
# ============================================================================================

TEST_MODE = "--testing" in sys.argv
SUFFIX = "_testing" if TEST_MODE else ""

# Carpetas y Archivos
DIR_CANALES = "canales"
DIR_DEBUG = ".debug"

def get_path(filename):
    base, ext = os.path.splitext(filename)
    if "/" in base:
        folder, name = base.rsplit("/", 1)
        return f"{folder}/{name}{SUFFIX}{ext}"
    return f"{base}{SUFFIX}{ext}"

FILE_ELCANO = get_path("elcano.m3u")
FILE_NEW_ERA = get_path("new_era.m3u")
FILE_EZDAKIT = get_path("ezdakit.m3u")
FILE_CORRESPONDENCIAS = get_path(f"{DIR_CANALES}/correspondencias.csv")
FILE_EVENTOS_CSV = get_path(f"{DIR_CANALES}/eventos_canales.csv")
FILE_EVENTOS_M3U = get_path("ezdakit_eventos.m3u")
FILE_DESCARTES = get_path(f"{DIR_CANALES}/descartes.csv")
FILE_PROXIES_LOG = f"{DIR_DEBUG}/proxies.log"

FILE_BLACKLIST = get_path(f"{DIR_CANALES}/lista_negra.csv") 
FILE_DIAL_MAP = get_path(f"{DIR_CANALES}/listado_canales.csv")
FILE_FORZADOS = get_path(f"{DIR_CANALES}/canales_forzados.csv")

# URLs
IPNS_HASH = "k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004"
URLS_ELCANO = [
    "https://ipfs.io/ipns/k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr/hashes.m3u",
    "https://gateway.pinata.cloud/ipns/k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr/hashes.m3u",
    "https://k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr.ipns.dweb.link/hashes.m3u"
]
URLS_NEW_ERA = [
    f"https://ipfs.io/ipns/{IPNS_HASH}/data/listas/lista_iptv.m3u",
    f"https://gateway.pinata.cloud/ipns/{IPNS_HASH}/data/listas/lista_iptv.m3u",
    f"https://{IPNS_HASH}.ipns.dweb.link/data/listas/lista_iptv.m3u"
]
URLS_AGENDA = [
    f"https://ipfs.io/ipns/{IPNS_HASH}/",
    f"https://cloudflare-ipfs.com/ipns/{IPNS_HASH}/",
    f"https://w3s.link/ipns/{IPNS_HASH}/",
    f"https://{IPNS_HASH}.ipns.dweb.link/"
]

HEADER_M3U = """#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"
#EXTVLCOPT:network-caching=1000
"""

# ============================================================================================
# GESTIÓN DE BASE DE DATOS SQLITE
# ============================================================================================

def init_db():
    """Inicia una DB en memoria para gestionar las búsquedas con SQL."""
    conn = sqlite3.connect(':memory:')
    c = conn.cursor()
    
    # Tabla CANALES (Equivalente a correspondencias.csv pero indexada)
    c.execute('''
        CREATE TABLE canales (
            ace_id TEXT PRIMARY KEY,
            nombre_supuesto TEXT,
            nombre_norm TEXT,  -- Columna auxiliar UPPER para búsquedas rápidas
            tvg_id TEXT,
            calidad TEXT
        )
    ''')
    
    # Índice para búsqueda súper rápida
    c.execute('CREATE INDEX idx_nombre_norm ON canales(nombre_norm)')
    conn.commit()
    return conn

def populate_db(conn, master_db):
    """Vuelca la lista maestra de Python a la tabla SQL."""
    c = conn.cursor()
    for item in master_db:
        # Guardamos el nombre tal cual y una versión normalizada (UPPER y limpia) para buscar
        nombre_real = item['nombre_supuesto']
        nombre_norm = nombre_real.upper().strip()
        
        c.execute('''
            INSERT OR REPLACE INTO canales (ace_id, nombre_supuesto, nombre_norm, tvg_id, calidad)
            VALUES (?, ?, ?, ?, ?)
        ''', (item['ace_id'], nombre_real, nombre_norm, item['final_tvg'], item['calidad_clean']))
    conn.commit()
    print(f"    [SQL] Base de datos poblada con {len(master_db)} canales.")

def search_channel_sql(conn, text_web):
    """
    Usa SQL para encontrar el canal. 
    Lógica: Exacto -> M+ Equivalente -> Sin Prefijo -> Con Prefijo
    """
    if not text_web: return "Unknown"
    
    c = conn.cursor()
    
    # 1. Preparar el input: Limpiar paréntesis y pasar a Mayúsculas
    clean_web = re.sub(r'\s*\(.*?\)', '', text_web).strip().upper()
    
    # --- INTENTO 1: Búsqueda Exacta ---
    c.execute('SELECT nombre_supuesto FROM canales WHERE nombre_norm = ? LIMIT 1', (clean_web,))
    row = c.fetchone()
    if row: return row[0]
    
    # --- PREPARAR VARIANTES PARA CONSULTA SQL ---
    # Generamos variantes lógicas basadas en M+ / MOVISTAR
    variantes = []
    
    # Si empieza por M+
    if clean_web.startswith("M+ "):
        variantes.append(clean_web.replace("M+ ", "MOVISTAR ")) # Variante extendida
        variantes.append(clean_web.replace("M+ ", ""))         # Variante recortada (sin prefijo)
        
    # Si empieza por MOVISTAR
    elif clean_web.startswith("MOVISTAR "):
        variantes.append(clean_web.replace("MOVISTAR ", "M+ ")) # Variante comprimida
        variantes.append(clean_web.replace("MOVISTAR ", ""))    # Variante recortada
        
    # Si no tiene prefijo, probamos a añadirselo (a veces la agenda dice LIGA y el canal es M+ LIGA)
    else:
        variantes.append(f"M+ {clean_web}")
        variantes.append(f"MOVISTAR {clean_web}")

    # --- INTENTO 2: Buscar cualquiera de las variantes ---
    if variantes:
        # Creamos una query dinámica: SELECT ... WHERE nombre_norm IN (?, ?, ?)
        placeholders = ','.join(['?'] * len(variantes))
        query = f'SELECT nombre_supuesto FROM canales WHERE nombre_norm IN ({placeholders})'
        c.execute(query, variantes)
        rows = c.fetchall()
        
        if rows:
            # Si hay varios matches (ej: encontró "LIGA DE CAMPEONES 2" y "M+ LIGA DE CAMPEONES 2")
            # Devolvemos el más corto (sin prefijo) como preferencia, o el primero que salga.
            # En SQL el resultado es una lista de tuplas [('Nombre1',), ('Nombre2',)]
            resultados = [r[0] for r in rows]
            # Ordenamos por longitud y devolvemos el más corto
            resultados.sort(key=len)
            return resultados[0]

    return "No Match"

# ============================================================================================
# FUNCIONES AUXILIARES (DESCARGA Y LIMPIEZA)
# ============================================================================================

def read_file_safe(path_obj):
    if not path_obj.exists(): return ""
    try:
        return path_obj.read_text(encoding='utf-8')
    except:
        return path_obj.read_text(encoding='latin-1', errors='ignore')

def download_file(urls, output_filename):
    print(f"   -> Descargando {output_filename}...")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    for url in urls:
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200 and "#EXTM3U" in r.text[:200]:
                Path(output_filename).write_text(r.text, encoding='utf-8')
                return True
        except: pass
    return False

def clean_channel_name(name, ace_id_suffix):
    """Limpieza visual, NO fuerza mayúsculas globales, deja el nombre 'natural'."""
    if not name: return ""
    name = re.sub(r'-->.*', '', name)
    terms = [r'1080p', r'720p', r'FHD', r'UHD', r'4K', r'HD', r'SD', r'HEVC', r'\|', r'vip']
    for term in terms:
        name = re.sub(term, '', name, flags=re.IGNORECASE)
    
    name = name.strip().rstrip(' -_')
    if ace_id_suffix and name.endswith(ace_id_suffix):
        name = name[:-4].strip()
    return name

def determine_quality(name):
    u = name.upper()
    if "4K" in u or "UHD" in u: return " (UHD)"
    if "1080" in u or "FHD" in u: return " (FHD)"
    return " (HD)"

# ============================================================================================
# PROCESAMIENTO PRINCIPAL
# ============================================================================================

def load_static_data():
    """Carga CSVs estáticos (Blacklist, Mapas, Forzados)"""
    bl = {}
    path_bl = Path(FILE_BLACKLIST)
    if path_bl.exists():
        reader = csv.DictReader(io.StringIO(read_file_safe(path_bl)))
        for row in reader:
            if row.get('ace_id'): bl[row['ace_id']] = row.get('canal_real', '')

    forced = {}
    path_fr = Path(FILE_FORZADOS)
    if path_fr.exists():
        # Remove BOM if present
        content = read_file_safe(path_fr).replace('\ufeff', '')
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

    dial_map = {}
    path_dm = Path(FILE_DIAL_MAP)
    if path_dm.exists():
        reader = csv.DictReader(io.StringIO(read_file_safe(path_dm)))
        for row in reader:
            dial = row.get('Dial_Movistar(M)', '').strip()
            if dial:
                dial_map[dial] = {'tvg': row.get('TV_guide_id'), 'name': row.get('Canal')}
    
    return bl, forced, dial_map

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
                    data[aid] = {'name': raw_name, 'tvg': mt.group(1) if mt else "Unknown", 'group': mg.group(1) if mg else "", 'url': url, 'source': source_tag}
        i += 1
    return data

def build_db_and_lists(blacklist, forced_channels):
    print(f"[3] Fusionando listas y creando DB SQL...")
    if not download_file(URLS_ELCANO, FILE_ELCANO) and not download_file(URLS_NEW_ERA, FILE_NEW_ERA):
        sys.exit("[ERROR] Fallo descarga listas")

    elcano = parse_m3u(FILE_ELCANO, "E")
    newera = parse_m3u(FILE_NEW_ERA, "N")
    
    all_ids = set(elcano.keys()) | set(newera.keys()) | set(forced_channels.keys())
    master_db = []
    
    ne_map = {v['name']: v['tvg'] for v in newera.values() if v['tvg'] != "Unknown"}

    for aid in all_ids:
        e = elcano.get(aid, {})
        n = newera.get(aid, {})
        f = forced_channels.get(aid)
        
        name_base = n.get('name') or e.get('name') or ""
        # Si falta tvg en Elcano, intentar recuperarlo de NewEra por nombre
        tvg = e.get('tvg')
        if not tvg or tvg == "Unknown":
            if e.get('name') in ne_map: tvg = ne_map[e.get('name')]
        
        nombre_supuesto = clean_channel_name(name_base, aid[-4:]) or "Desconocido"
        quality_tag = determine_quality(name_base)
        
        final_src = "N" if aid in newera else "E"
        final_url = n.get('url') or e.get('url')
        final_grp = n.get('group') or e.get('group') or "OTROS"
        final_tvg = n.get('tvg') if (n.get('tvg') and n.get('tvg') != "Unknown") else tvg or "Unknown"

        if f:
            nombre_supuesto = f['name']
            final_grp = f['group']
            final_tvg = f['tvg']
            q = f['quality'].upper()
            quality_tag = f" ({q})" if q else ""
            final_src = "F"
            if not final_url: final_url = f"acestream://{aid}"

        in_bl = "yes" if aid in blacklist else "no"
        
        master_db.append({
            'ace_id': aid,
            'nombre_e': e.get('name',''), 'nombre_ne': n.get('name',''),
            'tvg_e': e.get('tvg',''), 'tvg_ne': n.get('tvg',''),
            'nombre_supuesto': nombre_supuesto,
            'grupo_e': e.get('group',''), 'grupo_ne': n.get('group',''),
            'calidad_clean': quality_tag.replace('(','').replace(')','').strip(),
            'calidad_tag': quality_tag,
            'source': final_src, 'url': final_url,
            'final_group': final_grp, 'final_tvg': final_tvg,
            'in_blacklist': in_bl, 'blacklist_real_name': blacklist.get(aid, "")
        })
        
    master_db.sort(key=lambda x: (x['final_group'], x['nombre_supuesto']))
    
    # CREAR DB SQL Y POBLARLA
    conn = init_db()
    populate_db(conn, master_db)
    
    return master_db, conn

def get_html():
    scraper = cloudscraper.create_scraper()
    for url in URLS_AGENDA:
        try:
            print(f"    Probando {url}...")
            r = scraper.get(url, timeout=30)
            if r.status_code == 200 and "events-day" in r.text:
                return r.text
        except: pass
    return None

def process_agenda_with_sql(conn, dial_map, master_db):
    print(f"[6] Scraping Agenda y buscando con SQL...")
    html = get_html()
    if not html: return [], []
    
    # Crear un índice rápido de AceStream por TVG para asignar IDs después
    # (Ya que la DB SQL la usamos para buscar el nombre, pero necesitamos el ID)
    tvg_map = {}
    for item in master_db:
        t = item['final_tvg']
        if t and t != "Unknown":
            if t not in tvg_map: tvg_map[t] = []
            tvg_map[t].append(item)

    soup = BeautifulSoup(html, 'html.parser')
    events = []
    descartes = []
    
    for day in soup.find_all('div', class_='events-day'):
        date = day.get('data-date')
        if not date: continue
        
        for row in day.find_all('tr', class_='event-row'):
            evt_txt = row.get('data-event-id')
            comp = row.find('div', class_='competition-info')
            comp_txt = comp.get_text(strip=True) if comp else ""
            tds = row.find_all('td')
            hora = tds[0].get_text(strip=True) if tds else "00:00"
            if not evt_txt: evt_txt = tds[2].get_text(strip=True) if len(tds)>2 else "Evento"
            
            for ch in row.find_all('span', class_='channel-link'):
                raw_txt = ch.get_text().strip()
                
                # --- AQUÍ LA MAGIA DEL SQL ---
                nombre_db = search_channel_sql(conn, raw_txt)
                # -----------------------------
                
                # Intentar dial por si acaso
                dial_match = re.search(r'M(\d+)', raw_txt) or re.search(r'\((\d+)\)', raw_txt)
                dial = dial_match.group(1) if dial_match else None
                
                if dial and dial in dial_map:
                    tvg_target = dial_map[dial]['tvg']
                    nombre_csv = dial_map[dial]['name']
                    
                    matches = tvg_map.get(tvg_target, [])
                    if not matches:
                        descartes.append({'dial': dial, 'nombre': raw_txt, 'motivo': 'No streams'})
                        continue
                        
                    seen = set()
                    for m in matches:
                        if m['ace_id'] in seen: continue
                        seen.add(m['ace_id'])
                        events.append({
                            'acestream_id': m['ace_id'],
                            'dial_M': dial,
                            'tvg_id': tvg_target,
                            'fecha': date,
                            'hora': hora,
                            'evento': evt_txt,
                            'competición': comp_txt,
                            'nombre_canal': nombre_csv,
                            'canal_agenda': nombre_db, # Este viene directo de la DB
                            'calidad': m['calidad_clean'],
                            'lista_negra': m['in_blacklist'],
                            'calidad_tag': m['calidad_tag'],
                            'ace_prefix': m['ace_id'][:3],
                            'dia_m3u': date[5:]
                        })
                else:
                     descartes.append({'dial': '?', 'nombre': raw_txt, 'motivo': 'Unlisted'})
                     
    return events, descartes

# ============================================================================================
# MAIN
# ============================================================================================

def main():
    Path(DIR_CANALES).mkdir(exist_ok=True)
    
    bl, forced, dial_map = load_static_data()
    master_db, db_conn = build_db_and_lists(bl, forced)
    
    # 1. CSV Correspondencias
    print(f"[4] Generando {FILE_CORRESPONDENCIAS}...")
    with open(FILE_CORRESPONDENCIAS, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['acestream_id','nombre_e','nombre_ne','tvg-id_e','tvg-id_ne','nombre_supuesto','grupo_e','grupo_ne','calidad','lista_negra','canal_real'])
        w.writeheader()
        for i in master_db:
            w.writerow({k: i.get(k,'') for k in w.fieldnames}) # Map safe

    # 2. M3U Ezdakit
    print(f"[5] Generando {FILE_EZDAKIT}...")
    lines = [HEADER_M3U]
    for i in master_db:
        name = f"{i['nombre_supuesto']}{i['calidad_tag']} ({i['source']}-{i['ace_id'][:3]})"
        if i['in_blacklist'] == "yes": name += f" >>> {i['blacklist_real_name']}"
        grp = "ZZ_Canales_KO" if i['in_blacklist'] == "yes" else (i['final_group'] or "OTROS")
        lines.append(f'#EXTINF:-1 tvg-id="{i["final_tvg"]}" tvg-name="{name}" group-title="{grp}",{name}\n{i["url"]}')
    Path(FILE_EZDAKIT).write_text('\n'.join(lines), encoding='utf-8')
    
    # 3. Scraping y Eventos
    events, descartes = process_agenda_with_sql(db_conn, dial_map, master_db)
    
    # CSV Eventos
    print(f"[7] Generando {FILE_EVENTOS_CSV}...")
    events.sort(key=lambda x: (x['fecha'], x['hora']))
    with open(FILE_EVENTOS_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['acestream_id','dial_M','tvg_id','fecha','hora','evento','competición','nombre_canal','canal_agenda','calidad','lista_negra'])
        w.writeheader()
        for e in events:
            # Filtramos keys extras usadas para el M3U
            clean_e = {k: v for k, v in e.items() if k in w.fieldnames}
            w.writerow(clean_e)

    # M3U Eventos
    m3u_ev = [HEADER_M3U]
    for e in events:
        if e['lista_negra'] == "yes": continue
        full_name = f"{e['hora']}-{e['evento']} ({e['nombre_canal']}){e['calidad_tag']} ({e['ace_prefix']})"
        m3u_ev.append(f'#EXTINF:-1 group-title="{e["dia_m3u"]} {e["competición"]}" tvg-name="{full_name}",{full_name}\nhttp://127.0.0.1:6878/ace/getstream?id={e["acestream_id"]}')
    Path(FILE_EVENTOS_M3U).write_text('\n'.join(m3u_ev), encoding='utf-8')

    # Descartes
    print(f"[8] Generando {FILE_DESCARTES}...")
    with open(FILE_DESCARTES, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['dial','nombre','motivo'])
        w.writeheader()
        for d in descartes: w.writerow(d)

    db_conn.close()
    print("\n### PROCESO COMPLETADO")

if __name__ == "__main__":
    main()
