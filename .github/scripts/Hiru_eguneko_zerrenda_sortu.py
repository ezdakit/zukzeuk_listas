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
                r.encoding = 'utf-8' # Corrección de tildes
                return r.text
        except: continue
    return None

def clean_match_name(text):
    """Limpia el nombre del partido eliminando toda la basura de navegación"""
    if not text: return ""
    # Eliminar frases de sistema que se ven en tus archivos (5), (6) y (7)
    trash = [
        "Enlaces de disponibles", "Copiar ID", "Reproducir", "Ver Contenido", 
        "Descargar", "FHD", "HD", "SD", "NEW ERA", "ELCANO", "-->", "ID", 
        "Links", "Acestream", "Grid Lista", "Categorías", "Etiquetas", "()",
        "DAZN", "Eurosport 1", "Eurosport 2", "Teledeporte", "LaLiga"
    ]
    for t in trash:
        text = text.replace(t, "")
    
    # Eliminar hashes de 40 caracteres
    text = re.sub(r'[a-f0-9]{40}', '', text)
    # Limpiar espacios y símbolos
    text = re.sub(r'\s+', ' ', text).strip(" -:>()")
    return text

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # 1. Primero identificamos las competiciones reales buscando encabezados claros
    # Las webs de agenda suelen usar h3 o b para el nombre de la liga (ej: NCAA, 1RFEF)
    current_comp = "Otros"

    # Buscamos en todas las filas de la tabla
    for row in soup.find_all(['tr', 'h3', 'b']):
        row_text = row.get_text(" ", strip=True)
        
        # Ignorar bloques de menú (si el texto es demasiado largo y tiene palabras de menú)
        if "TODOS" in row_text.upper() and len(row_text) > 100:
            continue

        ids = ace_pattern.findall(str(row))

        # SI NO HAY IDs: Es un posible cambio de competición
        if not ids:
            cleaned = clean_match_name(row_text)
            if 2 < len(cleaned) < 30: # Una competición suele tener nombre corto
                current_comp = cleaned
            continue

        # SI HAY IDs: Es un partido
        # Buscamos la hora. Si no hay hora, es basura de menú.
        time_match = re.search(r'(\d{1,2}:\d{2})', row_text)
        if not time_match:
            continue
            
        event_time = time_match.group(1)
        
        # El nombre es lo que está justo después de la hora
        match_name = row_text.split(event_time)[-1]
        match_name = clean_match_name(match_name)
        
        if not match_name or len(match_name) < 3:
            match_name = "Evento Deportivo"

        # Añadimos los enlaces únicos de esa fila
        seen_ids = set()
        for aid in ids:
            if aid not in seen_ids:
                short_id = aid[:3]
                display_name = f"{event_time} {match_name}".strip()
                group_tag = f"{current_date} {current_comp}"

                entry = (
                    f'#EXTINF:-1 group-title="{group_tag}" tvg-name="{match_name}",{display_name} ({short_id})\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                )
                entries.append(entry)
                seen_ids.add(aid)
                
    return entries

def save_m3u(entries):
    if not entries: return
    # Eliminar duplicados globales
    unique_entries = []
    seen = set()
    for e in entries:
        if e not in seen:
            unique_entries.append(e)
            seen.add(e)

    full_content = HEADER_M3U + "\n\n" + "\n\n".join(unique_entries)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    # Historial
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
            save_m3u(entries)
            print(f"Lista creada con {len(entries)} canales.")
        else:
            print("No se encontraron partidos válidos.")

if __name__ == "__main__":
    main()
