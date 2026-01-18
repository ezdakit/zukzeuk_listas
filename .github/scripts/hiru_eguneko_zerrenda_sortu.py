import os
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import hashlib
import shutil
import time
from fake_useragent import UserAgent

# --- CONFIGURACIÓN ---
OUTPUT_FILE = "zz_eventos_all_ott.m3u"
HISTORY_DIR = "history"
MAX_HISTORY = 50

# URL Original (IPNS key)
IPNS_KEY = "k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004"
PATH_PARAMS = "/?tab=agenda"

# Lista de Gateways Públicos de IPFS para usar como "Proxies" y evitar bloqueos
# Esto rota la IP de salida y el dominio de acceso.
GATEWAYS = [
    "https://ipfs.io/ipns/",
    "https://dweb.link/ipns/",
    "https://cf-ipfs.com/ipns/",
    "https://gateway.ipfs.io/ipns/",
    "https://ipfs.eth.aragon.network/ipns/"
]

HEADER_M3U = """#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/EPG_dobleM.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"
#EXTVLCOPT:network-caching=1000
"""

def get_html_content():
    ua = UserAgent()
    
    for gateway in GATEWAYS:
        url = f"{gateway}{IPNS_KEY}{PATH_PARAMS}"
        headers = {'User-Agent': ua.random}
        print(f"Intentando conectar con: {gateway} ...")
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                print("Conexión exitosa.")
                return response.text
        except Exception as e:
            print(f"Fallo con {gateway}: {e}")
            continue
    
    return None

def clean_text(text):
    if not text: return ""
    return " ".join(text.split())

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    
    # Buscamos filas de tablas, estructura habitual en estas webs
    # Adaptado para buscar patrones generales ya que la web puede variar
    rows = soup.find_all('tr')
    
    current_date = "HOY" # Valor por defecto
    
    for row in rows:
        text_content = row.get_text(" ", strip=True)
        
        # Intentar detectar si es una fila de FECHA (Suele contener "Lunes", "Martes", o formato DD/MM)
        # Esto es heurístico, depende de cómo la web renderice la fecha separadora
        if len(text_content) < 30 and any(x in text_content.lower() for x in ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo', '202']):
             # Intentar extraer DD-MM
             match_date = re.search(r'(\d{1,2})[-/](\d{1,2})', text_content)
             if match_date:
                 current_date = f"{match_date.group(1).zfill(2)}-{match_date.group(2).zfill(2)}"
             continue

        # Buscar enlaces Acestream
        # A veces están en href="acestream://..." o en el texto
        links = row.find_all('a', href=True)
        acestreams = []
        
        for link in links:
            href = link['href']
            if href.startswith('acestream://'):
                aid = href.replace('acestream://', '')
                acestreams.append(aid)
            elif 'getstream?id=' in href:
                 aid = href.split('id=')[-1]
                 acestreams.append(aid)
        
        # Si no hay enlaces directos, buscar texto tipo (ID) o hashes de 40 caracteres
        if not acestreams:
             # Regex para buscar IDs de acestream (40 caracteres hex)
             ids_in_text = re.findall(r'\b[a-f0-9]{40}\b', str(row))
             acestreams.extend(ids_in_text)

        # Si encontramos acestreams en esta fila, procesamos el evento
        if acestreams:
            # Extracción de HORA y DATOS
            # Buscamos patrón de hora HH:MM
            time_match = re.search(r'(\d{1,2}:\d{2})', text_content)
            event_time = time_match.group(1) if time_match else "00:00"
            
            # Limpieza del nombre del evento
            # Quitamos la hora y caracteres raros para dejar el nombre limpio
            clean_name = text_content.replace(event_time, "").strip()
            # Intentar separar Categoría si existe (heurística simple)
            # Asumimos que la categoría es la primera palabra o está separada por guiones
            category = "Deportes"
            parts = clean_name.split('-')
            
            if len(parts) > 1:
                category = parts[0].strip()
                event_name = "-".join(parts[1:]).strip()
            else:
                event_name = clean_name
            
            # Formatear fecha para group-title
            # Si no detectamos fecha en filas separadoras, usamos la fecha de hoy
            if current_date == "HOY":
                now = datetime.now()
                formatted_date = now.strftime("%d-%m")
            else:
                formatted_date = current_date

            # Generar entradas
            for i, ace_id in enumerate(acestreams):
                # group-title: DD-MM Categoria
                group_title = f"{formatted_date} {category}"
                
                # nombre_del_canal: HH:MM Evento (Primeros3ID)
                short_id = ace_id[:3]
                channel_name = f"{event_time} {event_name} ({short_id})"
                
                # Construir la entrada
                entry = (
                    f'#EXTINF:-1 group-title="{group_title}" tvg-name="{channel_name}",{channel_name}\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={ace_id}'
                )
                entries.append(entry)

    return entries

def save_and_history(new_content):
    # 1. Crear contenido completo
    full_content = HEADER_M3U + "\n" + "\n".join(new_content)
    
    # 2. Verificar si el contenido ha cambiado respecto al actual
    file_changed = True
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            old_content = f.read()
        
        # Comparamos hash para eficiencia (o string directa)
        if old_content.strip() == full_content.strip():
            print("El contenido no ha cambiado. No se guarda historial.")
            file_changed = False
    
    # Guardamos el fichero principal siempre para actualizar headers/refresh
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    # 3. Gestión del historial
    if file_changed:
        if not os.path.exists(HISTORY_DIR):
            os.makedirs(HISTORY_DIR)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        history_filename = f"zz_eventos_{timestamp}.m3u"
        history_path = os.path.join(HISTORY_DIR, history_filename)
        
        shutil.copy(OUTPUT_FILE, history_path)
        print(f"Guardado en historial: {history_filename}")
        
        # Limpieza: Mantener solo los últimos 50
        files = sorted(os.listdir(HISTORY_DIR))
        files_full_path = [os.path.join(HISTORY_DIR, f) for f in files if f.endswith('.m3u')]
        
        # Ordenar por fecha de modificación
        files_full_path.sort(key=os.path.getmtime)
        
        while len(files_full_path) > MAX_HISTORY:
            file_to_remove = files_full_path.pop(0) # Borrar el más viejo
            os.remove(file_to_remove)
            print(f"Borrado por antigüedad: {file_to_remove}")

def main():
    html = get_html_content()
    if not html:
        print("No se pudo obtener el contenido HTML de ninguna fuente.")
        return

    entries = parse_agenda(html)
    
    if entries:
        print(f"Encontrados {len(entries)} canales/eventos.")
        save_and_history(entries)
    else:
        print("No se encontraron eventos con Acestream IDs.")

if __name__ == "__main__":
    main()
