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
                r.encoding = 'utf-8'
                return r.text
        except: continue
    return None

def clean_text(text):
    if not text: return ""
    # 1. Eliminar IDs y hashes
    text = re.sub(r'[a-f0-9]{40}', '', text)
    # 2. Eliminar palabras de botones y técnicos
    noise = [
        "Copiar ID", "Reproducir", "Ver Contenido", "Descargar", "FHD", "HD", "SD", 
        "NEW ERA", "ELCANO", "SPORT TV", "-->", "ID", "Links", "Acestream", "Grid", 
        "Lista", "Categorías", "Etiquetas", "TODOS", "Agenda Deportiva"
    ]
    for n in noise:
        text = text.replace(n, "")
    
    # 3. Limpieza final de espacios y símbolos
    text = re.sub(r'\s+', ' ', text)
    return text.strip(" -:>")

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # Palabras que indican que NO es una competición válida
    blacklist = ["TODOS", "CATEGORÍAS", "ETIQUETAS", "ACEStream", "AGENDA", "MENU"]
    
    current_comp = "Otros Deportes"

    # Buscamos todos los elementos que contengan texto o IDs
    for row in soup.find_all(['tr', 'div', 'h2', 'h3', 'b']):
        # Evitar procesar el menú de navegación superior
        raw_text = row.get_text(" ", strip=True)
        if any(word in raw_text.upper() for word in blacklist) and len(raw_text) > 100:
            continue

        ids = ace_pattern.findall(str(row))
        
        # 1. ¿Es un posible cambio de Competición?
        if not ids and row.name in ['h2', 'h3', 'b']:
            potential_comp = clean_text(raw_text)
            if 2 < len(potential_comp) < 40:
                current_comp = potential_comp
            continue

        # 2. Si hay IDs, es un evento
        if ids:
            # Capturamos el texto de la fila para sacar la hora y el nombre
            # Intentamos buscar el formato HH:MM
            time_match = re.search(r'(\d{1,2}:\d{2})', raw_text)
            event_time = time_match.group(1) if time_match else ""
            
            # El nombre del partido es lo que queda tras quitar hora, IDs y basura
            match_name = clean_text(raw_text.replace(event_time, ""))
            
            # Si el nombre es muy largo, es que ha pillado texto de más, lo acortamos
            if len(match_name) > 60:
                match_name = match_name[:60].rsplit(' ', 1)[0]

            if not match_name or len(match_name) < 3:
                match_name = "Evento"

            # Generar entradas
            for aid in list(dict.fromkeys(ids)):
                short_id = aid[:3]
                display_name = f"{event_time} {match_name}".strip()
                
                # Formatear group-title como pides: 18-01 Competición
                group_title = f"{current_date} {current_comp}".strip()

                entry = (
                    f'#EXTINF:-1 group-title="{group_title}" tvg-name="{match_name}",{display_name} ({short_id})\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                )
                entries.append(entry)
                
    return entries

def save_and_history(entries):
    # Eliminar duplicados manteniendo orden
    unique_entries = []
    seen = set()
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
            print(f"Éxito: {len(entries)} eventos procesados.")
        else:
            print("No se encontraron eventos.")
    else:
        print("Error en la descarga.")

if __name__ == "__main__":
    main()
