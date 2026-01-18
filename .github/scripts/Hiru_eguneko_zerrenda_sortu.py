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

# Lista de Gateways ACTUALIZADA y PRIORIZADA
# Pinata y 4everland suelen ser mucho más rápidos para IPNS
GATEWAYS = [
    "https://gateway.pinata.cloud/ipns/",
    "https://4everland.io/ipns/",
    "https://w3s.link/ipns/",
    "https://ipfs.io/ipns/",
    "https://dweb.link/ipns/",
    "https://flk-ipfs.xyz/ipns/"
]

HEADER_M3U = """#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/EPG_dobleM.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz" refresh="3600"
#EXTVLCOPT:network-caching=1000
"""

def get_html_content():
    ua = UserAgent()
    
    for gateway in GATEWAYS:
        url = f"{gateway}{IPNS_KEY}{PATH_PARAMS}"
        # Usamos un User-Agent de navegador real para evitar bloqueos simples
        headers = {
            'User-Agent': ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        print(f"Intentando conectar con: {gateway} ...")
        
        try:
            # Aumentamos timeout a 30 segundos porque IPNS es lento resolviendo
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                # Pequeña validación para asegurar que no nos devuelve una página de error del gateway
                if "agenda" in response.text.lower() or "deportes" in response.text.lower() or "<table" in response.text:
                    print(f"Conexión exitosa con {gateway}")
                    return response.text
                else:
                    print(f"Contenido sospechoso en {gateway}, probando siguiente...")
            else:
                print(f"Status code {response.status_code} en {gateway}")

        except Exception as e:
            # Convertimos el error a string corto para no ensuciar el log
            error_msg = str(e).split('(')[0]
            print(f"Fallo con {gateway}: {error_msg}")
            continue
    
    return None

def clean_text(text):
    if not text: return ""
    return " ".join(text.split())

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    
    rows = soup.find_all('tr')
    current_date = "HOY" 
    
    for row in rows:
        text_content = row.get_text(" ", strip=True)
        
        if len(text_content) < 30 and any(x in text_content.lower() for x in ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo', '202']):
             match_date = re.search(r'(\d{1,2})[-/](\d{1,2})', text_content)
             if match_date:
                 current_date = f"{match_date.group(1).zfill(2)}-{match_date.group(2).zfill(2)}"
             continue

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
        
        if not acestreams:
             ids_in_text = re.findall(r'\b[a-f0-9]{40}\b', str(row))
             acestreams.extend(ids_in_text)

        if acestreams:
            time_match = re.search(r'(\d{1,2}:\d{2})', text_content)
            event_time = time_match.group(1) if time_match else "00:00"
            
            clean_name = text_content.replace(event_time, "").strip()
            category = "Deportes"
            parts = clean_name.split('-')
            
            if len(parts) > 1:
                category = parts[0].strip()
                event_name = "-".join(parts[1:]).strip()
            else:
                event_name = clean_name
            
            if current_date == "HOY":
                now = datetime.now()
                formatted_date = now.strftime("%d-%m")
            else:
                formatted_date = current_date

            for i, ace_id in enumerate(acestreams):
                group_title = f"{formatted_date} {category}"
                short_id = ace_id[:3]
                channel_name = f"{event_time} {event_name} ({short_id})"
                
                entry = (
                    f'#EXTINF:-1 group-title="{group_title}" tvg-name="{channel_name}",{channel_name}\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={ace_id}'
                )
                entries.append(entry)

    return entries

def save_and_history(new_content):
    full_content = HEADER_M3U + "\n" + "\n".join(new_content)
    
    file_changed = True
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            old_content = f.read()
        
        if old_content.strip() == full_content.strip():
            print("El contenido no ha cambiado. No se guarda historial.")
            file_changed = False
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    if file_changed:
        if not os.path.exists(HISTORY_DIR):
            os.makedirs(HISTORY_DIR)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        history_filename = f"zz_eventos_{timestamp}.m3u"
        history_path = os.path.join(HISTORY_DIR, history_filename)
        
        shutil.copy(OUTPUT_FILE, history_path)
        print(f"Guardado en historial: {history_filename}")
        
        files = sorted(os.listdir(HISTORY_DIR))
        files_full_path = [os.path.join(HISTORY_DIR, f) for f in files if f.endswith('.m3u')]
        files_full_path.sort(key=os.path.getmtime)
        
        while len(files_full_path) > MAX_HISTORY:
            file_to_remove = files_full_path.pop(0)
            os.remove(file_to_remove)
            print(f"Borrado por antigüedad: {file_to_remove}")

def main():
    html = get_html_content()
    if not html:
        # Si fallan todos, lanzamos una excepción para que GitHub Actions marque el workflow como fallido
        print("ERROR CRÍTICO: No se pudo obtener contenido de ningún gateway.")
        exit(1)

    entries = parse_agenda(html)
    
    if entries:
        print(f"Encontrados {len(entries)} canales/eventos.")
        save_and_history(entries)
    else:
        print("No se encontraron eventos con Acestream IDs (posible cambio de estructura web o web vacía).")

if __name__ == "__main__":
    main()
