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
                r.encoding = 'utf-8' # Crucial para las tildes
                return r.text
        except: continue
    return None

def clean_text(text, is_comp=False):
    if not text: return ""
    # Ruido técnico a eliminar
    noise = [
        "FHD", "HD", "SD", "NEW ERA", "ELCANO", "SPORT TV", "VI FHD", "II FHD", "III FHD", 
        "IV FHD", "V FHD", "NEW LOOP", "Copiar ID", "Reproducir", "Ver Contenido", 
        "Descargar", "-->", "ID", "Links", "Acestream", "Agenda Deportiva"
    ]
    for n in noise:
        text = text.replace(n, "")
    
    # Eliminar hashes de 40 caracteres
    text = re.sub(r'[a-f0-9]{40}', '', text)
    # Limpiar espacios
    text = re.sub(r'\s+', ' ', text).strip(" -:>")
    
    # Si es competición y es demasiado larga, probablemente no lo sea
    if is_comp and len(text) > 40: return ""
    return text

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # Palabras que delatan que un bloque es un menú y no contenido
    menu_keywords = ["GRID", "LISTA CATEGORÍAS", "TODOS", "ETIQUETAS", "CATEGORÍAS:"]
    
    current_comp = "Deportes"

    # Buscamos todos los elementos que pueden ser contenedores
    for element in soup.find_all(['h2', 'h3', 'b', 'tr']):
        raw_text = element.get_text(" ", strip=True).upper()
        
        # 1. FILTRO: ¿Es un menú de navegación? Ignorar.
        if any(key in raw_text for key in menu_keywords) and len(raw_text) > 60:
            continue

        ids = ace_pattern.findall(str(element))

        # 2. ¿Es un título de competición? (h2, h3 o b sin IDs de acestream)
        if not ids and element.name in ['h2', 'h3', 'b']:
            potential_comp = clean_text(element.get_text(strip=True), is_comp=True)
            if potential_comp:
                current_comp = potential_comp
            continue

        # 3. ¿Es un evento? (Contiene IDs)
        if ids:
            # Buscamos la hora HH:MM en el texto del elemento
            row_text = element.get_text(" ", strip=True)
            time_match = re.search(r'(\d{1,2}:\d{2})', row_text)
            event_time = time_match.group(1) if time_match else ""
            
            # Limpiar el nombre del partido (quitando la competición si se repite)
            match_name = clean_text(row_text.replace(event_time, "").replace(current_comp, ""))
            
            if not match_name or len(match_name) < 3:
                match_name = "Evento"

            # Crear una entrada por cada ID único en esta fila
            for aid in list(dict.fromkeys(ids)):
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
    # Deduplicar manteniendo el orden
    final_list = []
    seen = set()
    for e in entries:
        if e not in seen:
            final_list.append(e)
            seen.add(e)

    content = HEADER_M3U + "\n\n" + "\n\n".join(final_list)
    
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
            print(f"Éxito: {len(entries)} eventos procesados correctamente.")
        else:
            print("No se encontraron eventos procesables.")
    else:
        print("Error al descargar el HTML.")

if __name__ == "__main__":
    main()
