import os
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import shutil
from fake_useragent import UserAgent

# --- CONFIGURACIÓN ---
OUTPUT_FILE = "zz_eventos_all_ott.m3u"
HISTORY_DIR = "history"
MAX_HISTORY = 50
IPNS_KEY = "k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004"
PATH_PARAMS = "/?tab=agenda"

# Gateways prioritarios
GATEWAYS = [
    "https://w3s.link/ipns/",
    "https://cloudflare-ipfs.com/ipns/",
    "https://dweb.link/ipns/",
    "https://ipfs.io/ipns/"
]

HEADER_M3U = """#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/EPG_dobleM.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"
#EXTVLCOPT:network-caching=1000
"""

def get_html_content():
    ua = UserAgent()
    for gateway in GATEWAYS:
        url = f"{gateway}{IPNS_KEY}{PATH_PARAMS}"
        headers = {
            'User-Agent': ua.random,
            'Accept': '*/*',
            'Cache-Control': 'no-cache'
        }
        print(f"Intentando conectar con: {gateway} ...")
        try:
            # Timeout largo para dar tiempo a que el gateway resuelva IPNS
            response = requests.get(url, headers=headers, timeout=60)
            if response.status_code == 200 and len(response.text) > 500:
                return response.text
        except Exception as e:
            print(f"Fallo en {gateway}")
    return None

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    
    # Expresión regular para capturar IDs de 40 caracteres (Hexadecimal)
    # Buscamos en todo el documento, incluso si está dentro de un script de JS
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # 1. Identificar bloques de eventos
    # Buscamos filas (tr) o cualquier elemento que contenga un ID de acestream
    # Si están "ocultos tras clic", suelen estar en atributos 'onclick', 'data-id', etc.
    blocks = soup.find_all(['tr', 'div', 'li', 'button'])
    
    current_date = datetime.now().strftime("%d-%m")
    
    for block in blocks:
        block_str = str(block)
        # Buscar IDs en cualquier parte del HTML del bloque (incluyendo atributos)
        found_ids = ace_pattern.findall(block_str)
        
        if found_ids:
            # Limpiar duplicados de IDs en el mismo bloque
            unique_ids = list(dict.fromkeys(found_ids))
            
            # Extraer texto visible para el nombre del evento
            full_text = block.get_text(" ", strip=True)
            
            # Buscar hora HH:MM
            time_match = re.search(r'(\d{1,2}:\d{2})', full_text)
            event_time = time_match.group(1) if time_match else "00:00"
            
            # Intentar detectar categoría (si está en negrita o antes de un guion)
            category = "Deporte"
            if " - " in full_text:
                category = full_text.split(" - ")[0].replace(event_time, "").strip()[:15]
            
            # Limpiar nombre del evento
            event_name = full_text.replace(event_time, "").replace(category, "").strip()
            # Si el nombre queda vacío o muy corto, usamos un genérico
            if len(event_name) < 3: event_name = "Evento Deportivo"

            for aid in unique_ids:
                group_title = f"{current_date} {category}"
                short_id = aid[:3]
                channel_name = f"{event_time} {event_name} ({short_id})"
                
                entry = (
                    f'#EXTINF:-1 group-title="{group_title}" tvg-name="{channel_name}",{channel_name}\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                )
                entries.append(entry)

    # 2. Si el parseo por bloques falló pero hay IDs en el HTML, hacemos extracción masiva
    if not entries:
        all_ids = ace_pattern.findall(html)
        if all_ids:
            print(f"Se encontraron {len(all_ids)} IDs sueltos. Generando lista de emergencia.")
            for i, aid in enumerate(list(dict.fromkeys(all_ids))):
                entries.append(
                    f'#EXTINF:-1 group-title="{current_date} Eventos" tvg-name="Canal {i+1} ({aid[:3]})",Canal {i+1} ({aid[:3]})\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                )
    
    return entries

def save_and_history(new_content):
    # Eliminar duplicados exactos
    new_content = list(dict.fromkeys(new_content))
    
    full_content = HEADER_M3U + "\n" + "\n".join(new_content)
    
    # Comprobar si existe el fichero y si ha cambiado
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            if f.read().strip() == full_content.strip():
                print("El contenido es idéntico al anterior. No se guarda historial.")
                return

    # Guardar el actual
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    # Guardar historial
    if not os.path.exists(HISTORY_DIR):
        os.makedirs(HISTORY_DIR)
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_path = os.path.join(HISTORY_DIR, f"zz_eventos_{ts}.m3u")
    shutil.copy(OUTPUT_FILE, history_path)
    
    # Mantener 50 ficheros
    h_files = sorted([os.path.join(HISTORY_DIR, f) for f in os.listdir(HISTORY_DIR)], key=os.path.getmtime)
    while len(h_files) > MAX_HISTORY:
        os.remove(h_files.pop(0))

def main():
    html = get_html_content()
    if not html:
        print("No se pudo obtener el HTML de la web.")
        exit(1)
    
    entries = parse_agenda(html)
    if entries:
        print(f"Éxito: Se han generado {len(entries)} entradas.")
        save_and_history(entries)
    else:
        print("No se encontró ningún ID de Acestream en el código.")
        # Opcional: imprimir una parte del HTML para ver qué está llegando
        print("Muestra del HTML recibido:", html[:500])

if __name__ == "__main__":
    main()
