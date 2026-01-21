import requests
from bs4 import BeautifulSoup
import re
import csv
import os
import datetime
import glob

# Configuración
URL_ORIGINAL = "https://ipfs.io/ipns/k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004/?tab=agenda"
FALLBACK_GATEWAYS = [
    "https://dweb.link/ipns/k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004/?tab=agenda",
    "https://w3s.link/ipns/k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004/?tab=agenda"
]

FILE_CSV = "canales/listado_canales.csv"
FILE_M3U_SOURCE = "ezdakit.m3u"
FILE_OUTPUT = "ezdakit_eventos.m3u"
DIR_HISTORY = "history"

HEADER_M3U = """#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/EPG_dobleM.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"
#EXTVLCOPT:network-caching=1000

"""

def get_html_content():
    urls = [URL_ORIGINAL] + FALLBACK_GATEWAYS
    for url in urls:
        try:
            print(f"Intentando conectar a: {url}")
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                return response.text
        except Exception as e:
            print(f"Error conectando a {url}: {e}")
            continue
    return None

def load_dial_mapping():
    """Carga el CSV y devuelve un dict {dial_movistar: tv_guide_id}"""
    mapping = {}
    if not os.path.exists(FILE_CSV):
        print(f"Advertencia: No se encuentra {FILE_CSV}")
        return mapping
    
    with open(FILE_CSV, mode='r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        for row in reader:
            dial = row.get('Dial_Movistar(M)')
            tvg_id = row.get('TV_guide_id')
            if dial and tvg_id:
                mapping[dial.strip()] = tvg_id.strip()
    return mapping

def load_acestreams():
    """Carga ezdakit.m3u y devuelve un dict {tvg_id: [lista_ids_acestream]}"""
    streams = {}
    if not os.path.exists(FILE_M3U_SOURCE):
        print(f"Advertencia: No se encuentra {FILE_M3U_SOURCE}")
        return streams

    with open(FILE_M3U_SOURCE, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    pattern = re.compile(r'tvg-id="([^"]+)".*?\n(http://127\.0\.0\.1:6878/ace/getstream\?id=([a-fA-F0-9]+))', re.DOTALL)
    
    matches = pattern.findall(content)
    for tvg_id, full_url, ace_id in matches:
        if tvg_id not in streams:
            streams[tvg_id] = []
        streams[tvg_id].append(ace_id)
        
    return streams

def parse_agenda(html, dial_map, stream_map):
    soup = BeautifulSoup(html, 'html.parser')
    agenda_tab = soup.find('div', id='agendaTab')
    if not agenda_tab:
        return []

    entries = []
    days = agenda_tab.find_all('div', class_='events-day')
    
    for day_div in days:
        date_str_iso = day_div.get('data-date')
        if not date_str_iso: continue
        
        dt_obj = datetime.datetime.strptime(date_str_iso, "%Y-%m-%d")
        date_formatted = dt_obj.strftime("%d-%m")

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
                match_m = re.search(r'\(M(\d+).*?\)', ch_text)
                
                if match_m:
                    dial = match_m.group(1)
                    tvg_id = dial_map.get(dial)
                    
                    if tvg_id:
                        ace_ids = stream_map.get(tvg_id, [])
                        for ace_id in ace_ids:
                            if ace_id in processed_ace_ids:
                                continue
                            processed_ace_ids.add(ace_id)
                            
                            ace_prefix = ace_id[:3]
                            final_name = f"{event_name} ({ace_prefix})"
                            group_title = f"{date_formatted} {competition}".strip()
                            
                            entry = f'#EXTINF:-1 group-title="{group_title}" tvg-name="{final_name}",{final_name}\n'
                            entry += f'http://127.0.0.1:6878/ace/getstream?id={ace_id}'
                            entries.append(entry)
                            
    return entries

def manage_history(new_content):
    os.makedirs(DIR_HISTORY, exist_ok=True)
    
    content_changed = True
    if os.path.exists(FILE_OUTPUT):
        with open(FILE_OUTPUT, 'r', encoding='utf-8') as f:
            old_content = f.read()
        if old_content == new_content:
            content_changed = False
            print("El contenido no ha cambiado. No se guarda histórico.")

    with open(FILE_OUTPUT, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    if content_changed:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        history_filename = os.path.join(DIR_HISTORY, f"ezdakit_eventos_{timestamp}.m3u")
        with open(history_filename, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Guardado en histórico: {history_filename}")
        
        files = sorted(glob.glob(os.path.join(DIR_HISTORY, "ezdakit_eventos_*.m3u")))
        while len(files) > 50:
            os.remove(files[0])
            files.pop(0)

def main():
    html = get_html_content()
    if not html:
        print("No se pudo obtener el HTML de ninguna fuente.")
        return

    dial_map = load_dial_mapping()
    stream_map = load_acestreams()
    entries = parse_agenda(html, dial_map, stream_map)
    full_content = HEADER_M3U + "\n".join(entries)
    manage_history(full_content)
    print("Proceso finalizado con éxito.")

if __name__ == "__main__":
    main()
