import requests
from bs4 import BeautifulSoup
import re
import csv
import os
import datetime
import glob
import sys

# --- CONFIGURACIÓN ---
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

def debug_info():
    """Imprime información sobre el entorno de ejecución."""
    print("--- INICIO DEPURACIÓN DEL SISTEMA ---")
    cwd = os.getcwd()
    print(f"[DEBUG] Directorio de trabajo actual: {cwd}")
    print(f"[DEBUG] Archivos en la raíz: {os.listdir(cwd)}")
    
    if os.path.exists("canales"):
        print(f"[DEBUG] Archivos en 'canales/': {os.listdir('canales')}")
    else:
        print("[ERROR CRÍTICO] La carpeta 'canales' NO existe.")
    
    if not os.path.exists(FILE_M3U_SOURCE):
        print(f"[ERROR CRÍTICO] El archivo fuente {FILE_M3U_SOURCE} NO existe en la raíz.")
    else:
        print(f"[DEBUG] Archivo {FILE_M3U_SOURCE} encontrado.")
    print("--- FIN DEPURACIÓN DEL SISTEMA ---")

def get_html_content():
    urls = [URL_ORIGINAL] + FALLBACK_GATEWAYS
    for url in urls:
        try:
            print(f"[CONEXIÓN] Intentando conectar a: {url}")
            response = requests.get(url, timeout=20)
            if response.status_code == 200:
                print(f"[ÉXITO] Conexión establecida. Bytes recibidos: {len(response.text)}")
                return response.text
            else:
                print(f"[FALLO] Status code: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Excepción conectando a {url}: {e}")
            continue
    return None

def load_dial_mapping():
    mapping = {}
    if not os.path.exists(FILE_CSV):
        print(f"[ERROR] No se encuentra el CSV: {FILE_CSV}")
        return mapping
    
    try:
        with open(FILE_CSV, mode='r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                dial = row.get('Dial_Movistar(M)')
                tvg_id = row.get('TV_guide_id')
                if dial and tvg_id:
                    mapping[dial.strip()] = tvg_id.strip()
        print(f"[DEBUG] Mapeo de canales cargado. Total entradas: {len(mapping)}")
    except Exception as e:
        print(f"[ERROR] Fallo leyendo CSV: {e}")
        
    return mapping

def load_acestreams():
    streams = {}
    if not os.path.exists(FILE_M3U_SOURCE):
        print(f"[ERROR] No se encuentra source M3U: {FILE_M3U_SOURCE}")
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
            
        print(f"[DEBUG] Streams cargados. Total IDs únicos con streams: {len(streams)}")
    except Exception as e:
        print(f"[ERROR] Fallo leyendo M3U source: {e}")

    return streams

def parse_agenda(html, dial_map, stream_map):
    print("[DEBUG] Iniciando parseo de HTML...")
    soup = BeautifulSoup(html, 'html.parser')
    agenda_tab = soup.find('div', id='agendaTab')
    
    if not agenda_tab:
        print("[ERROR] No se encontró <div id='agendaTab'> en el HTML. La estructura de la web puede haber cambiado.")
        # Intentar imprimir un resumen del HTML para ver qué hay
        print(f"[DEBUG] Primeros 500 caracteres del HTML: {html[:500]}")
        return []

    entries = []
    days = agenda_tab.find_all('div', class_='events-day')
    print(f"[DEBUG] Días encontrados en la agenda: {len(days)}")
    
    event_count = 0
    
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
                        if not ace_ids:
                             # print(f"[DEBUG] Canal M{dial} encontrado pero sin streams en ezdakit.m3u (TVG-ID: {tvg_id})")
                             pass
                             
                        for ace_id in ace_ids:
                            if ace_id in processed_ace_ids:
                                continue
                            processed_ace_ids.add(ace_id)
                            event_count += 1
                            
                            ace_prefix = ace_id[:3]
                            final_name = f"{event_name} ({ace_prefix})"
                            group_title = f"{date_formatted} {competition}".strip()
                            
                            entry = f'#EXTINF:-1 group-title="{group_title}" tvg-name="{final_name}",{final_name}\n'
                            entry += f'http://127.0.0.1:6878/ace/getstream?id={ace_id}'
                            entries.append(entry)
    
    print(f"[DEBUG] Total de eventos procesados y añadidos a la lista: {event_count}")
    return entries

def manage_history(new_content):
    print("[DEBUG] Gestionando historial y guardado de archivo...")
    try:
        os.makedirs(DIR_HISTORY, exist_ok=True)
        
        # Guardar fichero principal SIEMPRE, aunque esté vacío (salvo cabecera)
        with open(FILE_OUTPUT, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"[ÉXITO] Archivo {FILE_OUTPUT} generado correctamente.")
        
        # Comprobación de historial
        content_changed = True
        # Nota: Como acabamos de sobreescribir el fichero, la lógica de comparación
        # debería hacerse antes o comparar contra el último del historial.
        # Para simplificar, guardamos en historial si el último del historial es diferente.
        
        files_history = sorted(glob.glob(os.path.join(DIR_HISTORY, "ezdakit_eventos_*.m3u")))
        if files_history:
            last_history = files_history[-1]
            with open(last_history, 'r', encoding='utf-8') as f:
                old_content = f.read()
            if old_content == new_content:
                content_changed = False
                print("[INFO] El contenido es idéntico al último historial. No se crea copia nueva en history/.")

        if content_changed:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            history_filename = os.path.join(DIR_HISTORY, f"ezdakit_eventos_{timestamp}.m3u")
            with open(history_filename, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"[HISTORIAL] Guardado nuevo histórico: {history_filename}")
            
            # Limpieza
            files = sorted(glob.glob(os.path.join(DIR_HISTORY, "ezdakit_eventos_*.m3u")))
            while len(files) > 50:
                os.remove(files[0])
                print(f"[LIMPIEZA] Borrado histórico antiguo: {files[0]}")
                files.pop(0)
                
    except Exception as e:
        print(f"[ERROR CRÍTICO] Error al guardar archivos: {e}")
        sys.exit(1)

def main():
    debug_info()
    
    # 1. Obtener HTML
    html = get_html_content()
    if not html:
        print("[ERROR CRÍTICO] No se pudo obtener el HTML. Abortando.")
        sys.exit(1) # Salimos con error para que Github Actions lo marque en rojo

    # 2. Cargar datos locales
    dial_map = load_dial_mapping()
    if not dial_map:
        print("[ADVERTENCIA] El mapeo de canales está vacío. Verifica 'canales/listado_canales.csv'.")

    stream_map = load_acestreams()
    if not stream_map:
        print("[ADVERTENCIA] No se encontraron streams en 'ezdakit.m3u'.")

    # 3. Parsear
    entries = parse_agenda(html, dial_map, stream_map)
    
    if not entries:
        print("[ADVERTENCIA] La lista de entradas generada está vacía (0 eventos encontrados).")

    # 4. Generar archivo
    full_content = HEADER_M3U + "\n".join(entries)
    manage_history(full_content)
    
    print("[FIN] Script finalizado correctamente.")

if __name__ == "__main__":
    main()
