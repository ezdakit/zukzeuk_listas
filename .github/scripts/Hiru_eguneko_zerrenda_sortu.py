import os, requests, re, shutil
from bs4 import BeautifulSoup
from datetime import datetime
from fake_useragent import UserAgent

# --- CONFIGURACIÓN ---
OUTPUT_FILE = "zz_eventos_all_ott.m3u"
HISTORY_DIR = "history"
MAX_HISTORY = 50
IPNS_KEY = "k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004"
PATH_PARAMS = "/?tab=agenda"
GATEWAYS = ["https://w3s.link/ipns/", "https://cloudflare-ipfs.com/ipns/", "https://dweb.link/ipns/"]
HEADER_M3U = '#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml" refresh="3600"\n#EXTVLCOPT:network-caching=1000'

def get_html_content():
    ua = UserAgent()
    for gw in GATEWAYS:
        try:
            r = requests.get(f"{gw}{IPNS_KEY}{PATH_PARAMS}", headers={'User-Agent': ua.random}, timeout=30)
            if r.status_code == 200:
                r.encoding = 'utf-8' # Corrección de tildes (FEDERACIÓN)
                return r.text
        except: continue
    return None

def clean_name(text):
    """Limpia el ruido de los nombres de eventos y competiciones"""
    if not text: return ""
    # Palabras de control/basura a eliminar
    noise = [
        "FHD", "HD", "SD", "NEW ERA", "ELCANO", "SPORT TV", "VI FHD", "II FHD", "III FHD", 
        "IV FHD", "V FHD", "NEW LOOP", "Copiar ID", "Reproducir", "Ver Contenido", 
        "Descargar", "-->", "ID", "Links", "Acestream", "Agenda Deportiva", "Grid Lista"
    ]
    for n in noise:
        text = text.replace(n, "")
    
    # Quitar hashes (IDs)
    text = re.sub(r'[a-f0-9]{40}', '', text)
    # Limpiar espacios extra
    text = re.sub(r'\s+', ' ', text).strip(" -:>")
    return text

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    current_comp = "Deportes"
    
    # Bloques prohibidos (Menús de navegación que no queremos procesar)
    blacklist = ["TODOS", "CATEGORÍAS", "ETIQUETAS", "GRID LISTA"]

    # Buscamos todos los elementos de texto en orden de aparición
    for element in soup.find_all(['h2', 'h3', 'b', 'tr']):
        
        # 1. Ignorar si es un bloque de menú gigante
        raw_text = element.get_text(" ", strip=True)
        if any(word in raw_text.upper() for word in blacklist) and len(raw_text) > 80:
            continue

        ids = ace_pattern.findall(str(element))

        # 2. ¿Es un encabezado de Competición?
        if not ids and element.name in ['h2', 'h3', 'b']:
            potential_comp = clean_name(raw_text)
            if 2 < len(potential_comp) < 50:
                current_comp = potential_comp
            continue

        # 3. ¿Es una fila de evento?
        if ids:
            # Extraer hora (HH:MM)
            time_match = re.search(r'(\d{1,2}:\d{2})', raw_text)
            event_time = time_match.group(1) if time_match else ""
            
            # El nombre del partido es el texto de la fila limpiando hora y competición
            match_name = clean_name(raw_text.replace(event_time, "").replace(current_comp, ""))
            
            if not match_name or len(match_name) < 3:
                match_name = "Evento"

            # Una entrada por cada ID único
            unique_ids = list(dict.fromkeys(ids))
            for aid in unique_ids:
                short_id = aid[:3]
                display_name = f"{event_time} {match_name}".strip()
                group_title = f"{current_date} {current_comp}"

                entry = (
                    f'#EXTINF:-1 group-title="{group_title}" tvg-name="{match_name}",{display_name} ({short_id})\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                )
                entries.append(entry)
                
    return entries

def save_and_history(entries):
    # Eliminar duplicados exactos
    seen = set()
    unique_entries = []
    for e in entries:
        if e not in seen:
            unique_entries.append(e)
            seen.add(e)

    content = HEADER_M3U + "\n\n" + "\n\n".join(unique_entries)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    
    if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy(OUTPUT_FILE, os.path.join(HISTORY_DIR, f"zz_eventos_{ts}.m3u"))
    
    h_files = sorted([os.path.join(HISTORY_DIR, f) for f in os.listdir(HISTORY_DIR)], key=os.path.getmtime)
    while len(h_files) > MAX_HISTORY: os.remove(h_files.pop(0))

def main():
    html = get_html_content()
    if html:
        entries = parse_agenda(html)
        if entries:
            save_and_history(entries)
            print(f"Completado: {len(entries)} eventos guardados.")
        else:
            print("No se detectaron eventos.")
    else:
        print("Error al descargar.")

if __name__ == "__main__":
    main()
