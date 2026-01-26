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
print(f"### ZukZeuk SYSTEM: {'MODO TESTING 🛠️' if TEST_MODE else 'PRODUCCIÓN 🚀'}")
print(f"### Sufijo de archivos: '{SUFFIX}'")
print(f"######################################################################\n")

DIR_CANALES = "canales"
DIR_DEBUG = ".debug"

# Hashes IPNS
IPNS_ELCANO = "k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr"
IPNS_NEW_ERA = "k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004"

def get_gateway_urls(hash_ipns, path_suffix=""):
    """
    Genera la lista de URLs rotativas usando los 3 gateways seleccionados.
    Se eliminan los parámetros no-cache para asegurar la compatibilidad total.
    """
    return [
        f"https://ipfs.io/ipns/{hash_ipns}/{path_suffix}",
        f"https://{hash_ipns}.ipns.dweb.link/{path_suffix}",
        f"https://{hash_ipns}.ipns.w3s.link/{path_suffix}"
    ]

URLS_ELCANO = get_gateway_urls(IPNS_ELCANO, "hashes.m3u")
URLS_NEW_ERA = get_gateway_urls(IPNS_NEW_ERA, "data/listas/lista_iptv.m3u")
URLS_AGENDA = get_gateway_urls(IPNS_NEW_ERA, "?tab=agenda")

HEADER_M3U = """#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/master/guiatv.xml" refresh="3600"
#EXTVLCOPT:network-caching=1000
"""

# ============================================================================================
# GESTIÓN DE RUTAS
# ============================================================================================

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
FILE_BLACKLIST = get_path(f"{DIR_CANALES}/lista_negra.csv") 
FILE_DIAL_MAP = get_path(f"{DIR_CANALES}/listado_canales.csv")

# ============================================================================================
# UTILIDADES
# ============================================================================================

def read_file_safe(path_obj):
    if not path_obj.exists(): return ""
    return path_obj.read_text(encoding='utf-8', errors='replace')

def download_file(urls, output_filename):
    print(f"   -> Descargando {output_filename}...")
    scraper = cloudscraper.create_scraper()
    for url in urls:
        try:
            r = scraper.get(url, timeout=30)
            if r.status_code == 200:
                r.encoding = 'utf-8'
                Path(output_filename).write_text(r.text, encoding='utf-8')
                print(f"      ✅ [OK] Gateway: {url.split('/')[2]}")
                return True
        except: pass
    return False

def clean_channel_name(name, ace_id_suffix):
    if not name: return ""
    name = re.sub(r'-->.*', '', name)
    terms = [r'1080p', r'720p', r'FHD', r'UHD', r'4K', r'HD', r'SD', r'HEVC', r'\(ES\)', r'\|', r'vip', r'\bBAR\b']
    for term in terms: name = re.sub(term, '', name, flags=re.IGNORECASE)
    name = name.replace('  ', ' ').strip().rstrip(' -_')
    if ace_id_suffix and name.endswith(ace_id_suffix): name = name[:-4].strip()
    return name

def determine_quality(name):
    u = name.upper()
    if "4K" in u or "UHD" in u: return " (UHD)"
    if "1080" in u or "FHD" in u: return " (FHD)"
    return " (HD)"

# ============================================================================================
# CARGA DE DATOS
# ============================================================================================

def load_blacklist():
    print(f"[1] Cargando Lista Negra ({FILE_BLACKLIST})...")
    bl = {}
    path = Path(FILE_BLACKLIST)
    if not path.exists(): return bl
    content = read_file_safe(path)
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        aid = row.get('ace_id', '').strip()
        if aid: bl[aid] = row.get('canal_real', '').strip()
    print(f"    -> {len(bl)} IDs cargados.")
    return bl

def load_dial_mapping():
    print(f"[2] Cargando Mapeo de Diales ({FILE_DIAL_MAP})...")
    mapping = {}
    path = Path(FILE_DIAL_MAP)
    if not path.exists(): return mapping
    content = read_file_safe(path)
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        dial = row.get('Dial_Movistar(M)', '').strip()
        if dial: mapping[dial] = {'tvg': row.get('TV_guide_id', ''), 'name': row.get('Canal', '')}
    print(f"    -> {len(mapping)} canales mapeados.")
    return mapping

# ============================================================================================
# FUSIÓN M3U
# ============================================================================================

def parse_m3u(file_path, tag):
    data = {}
    path = Path(file_path)
    if not path.exists(): return data
    lines = read_file_safe(path).splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#EXTINF"):
            raw_name = line.split(',')[-1].strip()
            url = lines[i+1].strip() if i+1 < len(lines) else ""
            m = re.search(r"([0-9a-fA-F]{40})", url)
            if m:
                aid = m.group(1)
                tid = re.search(r'tvg-id="([^"]+)"', line)
                grp = re.search(r'group-title="([^"]+)"', line)
                data[aid] = {'name': raw_name, 'tvg': tid.group(1) if tid else "Unknown", 'group': grp.group(1) if grp else "", 'url': url, 'source': tag}
    return data

def build_master_list(blacklist):
    print(f"[3] Fusionando listas M3U...")
    download_file(URLS_ELCANO, FILE_ELCANO)
    download_file(URLS_NEW_ERA, FILE_NEW_ERA)
    elcano = parse_m3u(FILE_ELCANO, "E")
    newera = parse_m3u(FILE_NEW_ERA, "N")
    master_db = []
    all_ids = set(elcano.keys()) | set(newera.keys())
    for aid in all_ids:
        e, n = elcano.get(aid, {}), newera.get(aid, {})
        n_sup = clean_channel_name(n.get('name') or e.get('name'), aid[-4:])
        master_db.append({
            'ace_id': aid, 'nombre_e': e.get('name',''), 'nombre_ne': n.get('name',''),
            'tvg_e': e.get('tvg',''), 'tvg_ne': n.get('tvg',''), 'grupo_ne': n.get('group',''),
            'nombre_supuesto': n_sup, 'calidad_tag': determine_quality(n.get('name','') + e.get('name','')),
            'url': n.get('url') or e.get('url'), 'final_tvg': n.get('tvg') if n.get('tvg') != "Unknown" else e.get('tvg','Unknown'),
            'in_bl': "yes" if aid in blacklist else "no", 'bl_real': blacklist.get(aid, "")
        })
    master_db.sort(key=lambda x: (x['grupo_ne'] or "ZZZ", x['nombre_supuesto']))
    print(f"    -> {len(master_db)} canales únicos procesados.")
    return master_db

# ============================================================================================
# SCRAPING AGENDA
# ============================================================================================

def scrape_events(dial_map, master_db):
    print(f"[6] Scraping de Agenda Deportiva...")
    Path(DIR_DEBUG).mkdir(exist_ok=True)
    
    tvg_index = {}
    for item in master_db:
        if item['final_tvg'] != "Unknown":
            tvg_index.setdefault(item['final_tvg'], []).append(item)

    scraper = cloudscraper.create_scraper()
    final_days = []

    for url in URLS_AGENDA:
        try:
            print(f"    Probando gateway: {url.split('/')[2]}...")
            r = scraper.get(url, timeout=35)
            if r.status_code == 200:
                Path(f"{DIR_DEBUG}/agenda_debug.html").write_bytes(r.content)
                soup = BeautifulSoup(r.content, 'html.parser', from_encoding='utf-8')
                days = soup.find_all('div', class_='events-day')
                if days:
                    final_days = days
                    print(f"    ✅ Éxito: {len(days)} bloques de fechas encontrados.")
                    break
        except: pass

    if not final_days:
        print("    ❌ ERROR: Ningún gateway devolvió contenido válido.")
        return []

    events_list = []
    for day_div in final_days:
        date_iso = day_div.get('data-date', 'Unknown')
        rows = day_div.find_all('tr', class_='event-row')
        for row in rows:
            comp_div = row.find('div', class_='competition-info')
            competition = comp_div.get_text(" ", strip=True) if comp_div else "Otros"
            
            tds = row.find_all('td')
            if len(tds) < 3: continue
            
            hora = tds[0].get_text(strip=True)
            event_id = row.get('data-event-id', '').strip()
            event_clean = re.sub(r'^\d{2}:\d{2}-', '', event_id)
            
            if not event_clean or "-" not in event_clean or len(event_clean) < 5:
                match_info = row.find('div', class_='match-info')
                if match_info:
                    teams = match_info.find_all('span', class_='team-name')
                    event_clean = f"{teams[0].get_text(strip=True)} - {teams[1].get_text(strip=True)}" if len(teams) >= 2 else match_info.get_text(" ", strip=True)
                else:
                    event_clean = tds[2].get_text(" ", strip=True)
            
            event_clean = event_clean.replace("-", " - ") if "-" in event_clean and " - " not in event_clean else event_clean
            event_clean = re.sub(r'\s+', ' ', event_clean).strip()
            
            channels = row.find_all('span', class_='channel-link')
            for ch in channels:
                m = re.search(r'\((?:M)?(\d+).*?\)', ch.get_text())
                if m:
                    dial = m.group(1)
                    map_info = dial_map.get(dial)
                    if map_info:
                        for stream in tvg_index.get(map_info['tvg'], []):
                            events_list.append({
                                'acestream_id': stream['ace_id'], 'dial_M': dial, 'tvg_id': map_info['tvg'],
                                'fecha': date_iso, 'hora': hora, 'evento': event_clean,
                                'competición': competition, 'nombre_canal': map_info['name'],
                                'calidad_tag': stream['calidad_tag'], 'in_bl': stream['in_bl']
                            })
    print(f"    -> {len(events_list)} eventos vinculados encontrados.")
    return events_list

# ============================================================================================
# GENERADORES
# ============================================================================================

def generate_files(db, ev_list):
    # 1. Correspondencias
    print(f"[4] Generando {FILE_CORRESPONDENCIAS}...")
    with open(FILE_CORRESPONDENCIAS, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['acestream_id','nombre_e','nombre_ne','tvg-id_e','tvg-id_ne','nombre_supuesto','grupo_e','grupo_ne','calidad','lista_negra','canal_real'])
        w.writeheader()
        for i in db:
            w.writerow({'acestream_id':i['ace_id'],'nombre_e':i['nombre_e'],'nombre_ne':i['nombre_ne'],'tvg-id_e':i['tvg_e'],'tvg-id_ne':i['tvg_ne'],'nombre_supuesto':i['nombre_supuesto'],'grupo_ne':i['grupo_ne'],'calidad':i['calidad_tag'].strip(' ()'),'lista_negra':i['in_bl'],'canal_real':i['bl_real']})

    # 2. M3U Maestro
    print(f"[5] Generando {FILE_EZDAKIT}...")
    m3u = HEADER_M3U + "\n"
    for i in db:
        grp = "ZZ_Canales_KO" if i["in_bl"]=="yes" else (i["grupo_ne"] or "OTROS")
        name = f"{i['nombre_supuesto']}{i['calidad_tag']}"
        if i["in_bl"] == "yes":
            name += f" >>> {i['bl_real']}" if i['bl_real'] else " >>> BLACKLIST"
        m3u += f'#EXTINF:-1 tvg-id="{i["final_tvg"]}" group-title="{grp}",{name}\n{i["url"]}\n'
    Path(FILE_EZDAKIT).write_text(m3u, encoding='utf-8')

    # 3. Eventos
    if ev_list:
        print(f"[7] Generando {FILE_EVENTOS_CSV} y {FILE_EVENTOS_M3U}...")
        ev_list.sort(key=lambda x: (x['fecha'], x['hora']))
        with open(FILE_EVENTOS_CSV, 'w', newline='', encoding='utf-8-sig') as f:
            fields = ['acestream_id','dial_M','tvg_id','fecha','hora','evento','competición','nombre_canal','calidad','lista_negra']
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for ev in ev_list:
                w.writerow({'acestream_id':ev['acestream_id'],'dial_M':ev['dial_M'],'tvg_id':ev['tvg_id'],'fecha':ev['fecha'],'hora':ev['hora'],'evento':ev['evento'],'competición':ev['competición'],'nombre_canal':ev['nombre_canal'],'lista_negra':ev['in_bl']})
        
        m3u_ev = HEADER_M3U + "\n"
        for ev in ev_list:
            if ev['in_bl'] == 'no':
                m3u_ev += f'#EXTINF:-1 group-title="{ev["fecha"]} {ev["competición"]}",{ev["hora"]}-{ev["evento"]} ({ev["nombre_canal"]}){ev["calidad_tag"]}\nhttp://127.0.0.1:6878/ace/getstream?id={ev["acestream_id"]}\n'
        Path(FILE_EVENTOS_M3U).write_text(m3u_ev, encoding='utf-8')

if __name__ == "__main__":
    bl = load_blacklist()
    dm = load_dial_mapping()
    db = build_master_list(bl)
    ev = scrape_events(dm, db)
    generate_files(db, ev)
    print("\n✅ PROCESO COMPLETADO EXITOSAMENTE.")
