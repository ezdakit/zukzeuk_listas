import cloudscraper
from bs4 import BeautifulSoup
import re
import csv
import os
import datetime
import glob
import sys
import time

# --- CONFIGURACIÓN ---
IPNS_HASH = "k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004"

# GATEWAYS
GATEWAYS = [
    f"https://cf-ipfs.com/ipns/{IPNS_HASH}/?tab=agenda",
    f"https://{IPNS_HASH}.ipns.cf-ipfs.com/?tab=agenda",
    f"https://ipfs.io/ipns/{IPNS_HASH}/?tab=agenda",
    f"https://{IPNS_HASH}.ipns.dweb.link/?tab=agenda",
    f"https://{IPNS_HASH}.ipns.w3s.link/?tab=agenda",
    f"https://gateway.ipfs.io/ipns/{IPNS_HASH}/?tab=agenda"
]

FILE_CSV = "canales/listado_canales.csv"
FILE_M3U_SOURCE = "ezdakit.m3u"
FILE_BLACKLIST = "canales/lista_negra.csv"
FILE_OUTPUT = "ezdakit_eventos.m3u"
DIR_HISTORY = "history"

HEADER_M3U = """#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/EPG_dobleM.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"
#EXTVLCOPT:network-caching=1000

"""

def debug_info():
    print("--- INICIO DEPURACIÓN DEL SISTEMA ---")
    cwd = os.getcwd()
    print(f"[DEBUG] Directorio: {cwd}")
    if os.path.exists("canales"):
        print(f"[DEBUG] Carpeta 'canales' OK.")
    else:
        print("[ERROR CRÍTICO] Falta carpeta 'canales'.")
    
    if os.path.exists(FILE_M3U_SOURCE):
        print(f"[DEBUG] Archivo {FILE_M3U_SOURCE} OK.")
    else:
        print(f"[ERROR CRÍTICO] Falta archivo {FILE_M3U_SOURCE}.")
        
    if os.path.exists(FILE_BLACKLIST):
        print(f"[DEBUG] Archivo lista negra encontrado: {FILE_BLACKLIST}")
    else:
        print(f"[INFO] No existe lista negra ({FILE_BLACKLIST}), se continuará sin filtrar.")
        
    print("--- FIN DEPURACIÓN ---")

def get_html_content():
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )

    for url in GATEWAYS:
        try:
            print(f"[CONEXIÓN] Probando: {url}")
            response = scraper.get(url, timeout=90)
            
            if response.status_code == 200:
                response.encoding = 'utf-8'
                print(f"[ÉXITO] Datos recibidos ({len(response.text)} bytes) desde {url}")
                return response.text
            else:
                print(f"[FALLO] Status code {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Fallo en {url}: {e}")
            
        time.sleep(2)
        
    return None

def load_blacklist():
    """Carga los IDs de la lista negra desde un CSV (columna ace_id)."""
    blacklist = set()
    if not os.path.exists(FILE_BLACKLIST):
        return blacklist
    
    try:
        with open(FILE_BLACKLIST, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ace_id = row.get('ace_id')
                if ace_id:
                    clean_id = ace_id.strip()
                    if clean_id and not clean_id.startswith("#"):
                        blacklist.add(clean_id)
                        
        print(f"[DEBUG] Lista negra cargada: {len(blacklist)} IDs ignorados.")
    except Exception as e:
        print(f"[ERROR] Leyendo lista negra: {e}")
        
    return blacklist

def load_dial_mapping():
    mapping = {}
    if not os.path.exists(FILE_CSV):
        print(f"[ERROR] No existe {FILE_CSV}")
        return mapping
    
    try:
        with open(FILE_CSV, mode='r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                dial = row.get('Dial_Movistar(M)')
                tvg_id = row.get('TV_guide_id')
                if dial and tvg_id:
                    mapping[dial.strip()] = tvg_id.strip()
        print(f"[DEBUG] CSV cargado: {len(mapping)} canales.")
    except Exception as e:
        print(f"[ERROR] Fallo CSV: {e}")
    return mapping

def load_acestreams():
    streams = {}
    if not os.path.exists(FILE_M3U_SOURCE):
        print(f"[ERROR] No existe {FILE_M3U_SOURCE}")
        return streams

    try:
        with open(FILE_M3U_SOURCE, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        pattern = re.compile(r'tvg-id="([^"]+)".*?\n(http://127\.0\.0\.1:6878/ace/getstream\?id=([a-fA-F0-9]+))', re.DOTALL)
        matches = pattern.findall(content)
        
        for tvg_id, full_url, ace_id in matches:
            if tvg_id not in streams:
                streams[tvg_id] = []
            streams[tvg_id].append(ace_id)
            
        print(f"[DEBUG] M3U Source cargado: {len(streams)} canales.")
    except Exception as e:
        print(f"[ERROR] Fallo M3U: {e}")
    return streams

def parse_agenda(html, dial_map, stream_map, blacklist):
    print("[DEBUG] Analizando HTML...")
    soup = BeautifulSoup(html, 'html.parser')
    agenda_tab = soup.find('div', id='agendaTab')
    
    if not agenda_tab:
        print("[ERROR] No se encontró la sección 'agendaTab'.")
        print(f"[DEBUG DUMP] Inicio del HTML recibido: {html[:500]}")
        return []

    entries = []
    days = agenda_tab.find_all('div', class_='events-day')
    print(f"[DEBUG] Días encontrados: {len(days)}")
    
    event_count = 0
    skipped_count = 0
    
    for day_div in days:
        date_str_iso = day_div.get('data-date')
        if not date_str_iso: continue
        
        try:
            dt_obj = datetime.datetime.strptime(date_str_iso, "%Y-%m-%d")
            date_formatted = dt_obj.strftime("%d-%m")
        except ValueError:
            continue

        rows = day_div.find_all('tr', class_='event-row')
        for row in rows:
            event_name = row.get('data-event-id')
            
            comp_div = row.find('div', class_='competition-info')
            competition = ""
            if comp_div:
                comp_span = comp_div.find('span', class_='competition-name')
                if comp_span:
                    competition = comp_span.get_text(strip=True)

            channels = row.find_all('span', class_='channel-link')
            processed_ace_ids = set() 

            for ch in channels:
                ch_text = ch.get_text()
                
                # --- CAMBIO REALIZADO AQUÍ ---
                # Regex modificada: (?:M)? hace que la M sea opcional.
                # Captura: (M55) -> 55, (55) -> 55
                match_m = re.search(r'\((?:M)?(\d+).*?\)', ch_text)
                
                if match_m:
                    dial = match_m.group(1)
                    tvg_id = dial_map.get(dial)
                    
                    if tvg_id:
                        ace_ids = stream_map.get(tvg_id, [])
                        for ace_id in ace_ids:
                            # --- FILTRO LISTA NEGRA ---
                            if ace_id in blacklist:
                                skipped_count += 1
                                continue

                            if ace_id in processed_ace_ids:
                                continue
                            processed_ace_ids.add(ace_id)
                            event_count += 1
                            
                            ace_prefix = ace_id[:3]
                            
                            # Añadimos tvg_id al final del nombre
                            final_name = f"{event_name} ({ace_prefix}) ({tvg_id})"
                            
                            group_title = f"{date_formatted} {competition}".strip()
                            
                            entry = f'#EXTINF:-1 group-title="{group_title}" tvg-name="{final_name}",{final_name}\n'
                            entry += f'http://127.0.0.1:6878/ace/getstream?id={ace_id}'
                            entries.append(entry)
    
    print(f"[DEBUG] Total eventos generados: {event_count}")
    if skipped_count > 0:
        print(f"[DEBUG] Total IDs ignorados por lista negra: {skipped_count}")
    return entries

def manage_history(new_content):
    try:
        os.makedirs(DIR_HISTORY, exist_ok=True)
        
        with open(FILE_OUTPUT, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"[ÉXITO] Generado {FILE_OUTPUT}")
        
        content_changed = True
        files_history = sorted(glob.glob(os.path.join(DIR_HISTORY, "ezdakit_eventos_*.m3u")))
        
        if files_history:
            last_history = files_history[-1]
            try:
                with open(last_history, 'r', encoding='utf-8') as f:
                    old_content = f.read()
                if old_content == new_content:
                    content_changed = False
                    print("[INFO] Sin cambios respecto al último historial.")
            except:
                pass

        if content_changed:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            history_filename = os.path.join(DIR_HISTORY, f"ezdakit_eventos_{timestamp}.m3u")
            with open(history_filename, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"[HISTORIAL] Creado: {history_filename}")
            
            files = sorted(glob.glob(os.path.join(DIR_HISTORY, "ezdakit_eventos_*.m3u")))
            while len(files) > 50:
                os.remove(files[0])
                print(f"[LIMPIEZA] Eliminado antiguo: {files[0]}")
                files.pop(0)
                
    except Exception as e:
        print(f"[ERROR CRÍTICO] Gestionando ficheros: {e}")
        sys.exit(1)

def main():
    debug_info()
    
    html = get_html_content()
    if not html:
        print("[ERROR CRÍTICO] Fallo total de conexión con todos los gateways IPFS.")
        sys.exit(1)

    dial_map = load_dial_mapping()
    stream_map = load_acestreams()
    blacklist = load_blacklist()
    
    entries = parse_agenda(html, dial_map, stream_map, blacklist)
    
    full_content = HEADER_M3U + "\n".join(entries)
    manage_history(full_content)
    print("[FIN] Script finalizado.")

if __name__ == "__main__":
    main()
