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
            url = f"{gw}{IPNS_KEY}{PATH_PARAMS}"
            r = requests.get(url, headers={'User-Agent': ua.random}, timeout=40)
            if r.status_code == 200:
                # Forzamos UTF-8 para evitar problemas de tildes (Ã“ -> Ó)
                r.encoding = 'utf-8'
                return r.text
        except: continue
    return None

def clean_text(text, remove_list):
    """Limpia el ruido del texto de forma agresiva"""
    for item in remove_list:
        text = text.replace(item, "")
    # Quitar flechas, hashes de 40 caracteres y espacios múltiples
    text = re.sub(r'-->|-->|ID|Copiar|Reproducir', '', text)
    text = re.sub(r'[a-f0-9]{40}', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip(" -:>")

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # Palabras basura para limpiar títulos
    noise = ["FHD", "HD", "SD", "NEW ERA", "ELCANO", "SPORT TV", "VI FHD", "II FHD", "III FHD", "IV FHD", "V FHD"]
    
    current_competition = "Deportes"

    # Buscamos todos los contenedores principales (filas de tabla o divs de evento)
    # Analizamos todos los elementos del body en orden
    for element in soup.find_all(['tr', 'div', 'h2', 'h3']):
        
        # 1. ¿Es una cabecera de competición? 
        # Si es un texto corto, sin IDs de acestream, y no es basura
        raw_text = element.get_text(" ", strip=True)
        ids = ace_pattern.findall(str(element))
        
        if not ids:
            if 2 < len(raw_text) < 50 and not any(x in raw_text for x in ["Categorías", "Etiquetas", "TODOS"]):
                current_competition = clean_text(raw_text, noise)
            continue

        # 2. Si tiene IDs, es un evento. 
        # Buscamos la información dentro de ESTE contenedor (la fila completa)
        # Extraer hora (HH:MM)
        time_match = re.search(r'(\d{1,2}:\d{2})', raw_text)
        event_time = time_match.group(1) if time_match else ""
        
        # El nombre del partido es el texto de la fila quitando la hora, los IDs y el ruido
        match_name = clean_text(raw_text, noise + [event_time, current_competition])
        
        if len(match_name) < 3: match_name = "Evento Deportivo"

        # Generar una entrada por cada ID único encontrado en esta fila
        unique_ids = []
        for aid in ids:
            if aid not in unique_ids:
                unique_ids.append(aid)
                
                short_id = aid[:3]
                display_name = f"{event_time} {match_name}".strip()
                
                # Limpiar el group-title de restos de flechas o "FHD"
                clean_group = f"{current_date} {current_competition}".replace("-->", "").strip()
                clean_group = re.sub(r'\s+', ' ', clean_group)

                entry = (
                    f'#EXTINF:-1 group-title="{clean_group}" tvg-name="{match_name}",{display_name} ({short_id})\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                )
                entries.append(entry)
    
    return entries

def save_and_history(new_content):
    # Eliminar duplicados exactos
    seen = set()
    unique_entries = []
    for x in unique_entries_filter := new_content:
        if x not in seen:
            unique_entries.append(x)
            seen.add(x)
            
    full_content = HEADER_M3U + "\n\n" + "\n\n".join(unique_entries)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy(OUTPUT_FILE, os.path.join(HISTORY_DIR, f"zz_eventos_{ts}.m3u"))
    
    h_files = sorted([os.path.join(HISTORY_DIR, f) for f in os.listdir(HISTORY_DIR)], key=os.path.getmtime)
    while len(h_files) > MAX_HISTORY: os.remove(h_files.pop(0))

def main():
    html = get_html_content()
    if not html: 
        print("No se pudo obtener el contenido.")
        return
    
    entries = parse_agenda(html)
    if entries:
        print(f"Éxito: {len(entries)} canales generados correctamente.")
        save_and_history(entries)
    else:
        print("No se encontraron eventos procesables.")

if __name__ == "__main__":
    main()
