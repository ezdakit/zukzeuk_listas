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

GATEWAYS = ["https://w3s.link/ipns/", "https://cloudflare-ipfs.com/ipns/", "https://dweb.link/ipns/", "https://ipfs.io/ipns/"]

HEADER_M3U = '#EXTM3U url-tvg="https://github.com/davidmuma/EPG_dobleM/raw/refs/heads/master/EPG_dobleM.xml" refresh="3600"\n#EXTVLCOPT:network-caching=1000'

def get_html_content():
    ua = UserAgent()
    for gw in GATEWAYS:
        try:
            r = requests.get(f"{gw}{IPNS_KEY}{PATH_PARAMS}", headers={'User-Agent': ua.random}, timeout=40)
            if r.status_code == 200: return r.text
        except: continue
    return None

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # Variables de estado
    current_competition = "Deportes"
    
    # Palabras basura a limpiar del nombre del partido
    noise = ["Copiar ID", "Reproducir", "-->", "NEW ERA", "ELCANO", "SPORT TV", "FHD", "HD", "SD", "VI FHD"]

    # Buscamos todos los elementos que pueden contener texto (filas, celdas, divs, negritas)
    # Analizamos en orden de aparición en el HTML
    elements = soup.find_all(['tr', 'td', 'div', 'b', 'strong', 'h1', 'h2', 'h3'])

    for el in elements:
        # Evitamos procesar el mismo texto varias veces si está anidado
        if el.find(['tr', 'div']): continue 
        
        text = el.get_text(" ", strip=True)
        if not text or len(text) < 2: continue
        
        ids = ace_pattern.findall(str(el))

        if not ids:
            # Si NO hay ID y el texto es corto, probablemente es un nombre de competición
            # Ignoramos textos de interfaz como "Categorías", "Etiquetas", etc.
            if len(text) < 40 and not any(x in text for x in ["Categorías", "Etiquetas", "TODOS", "Copiar"]):
                # Si el texto termina en un número (ej: "DAZN 24"), limpiamos el número
                current_competition = re.sub(r'\s\d+$', '', text).strip()
            continue
        else:
            # Si HAY ID, es un evento/partido
            for aid in list(dict.fromkeys(ids)):
                match_name = text
                
                # 1. Limpiar el ID del nombre
                match_name = re.sub(r'[a-f0-9]{40}', '', match_name)
                
                # 2. Limpiar palabras de ruido
                for n in noise:
                    match_name = match_name.replace(n, "")
                
                # 3. Quitar la competición del nombre del partido si está repetida
                match_name = match_name.replace(current_competition, "")
                
                # 4. Extraer hora si existe (HH:MM)
                time_match = re.search(r'(\d{1,2}:\d{2})', match_name)
                event_time = time_match.group(1) if time_match else ""
                match_name = match_name.replace(event_time, "").strip(" -:>")
                
                # Limpieza final de espacios
                match_name = re.sub(r'\s+', ' ', match_name).strip()
                
                if not match_name: match_name = "Evento"
                
                display_name = f"{event_time} {match_name}".strip()
                short_id = aid[:3]
                
                # Generar la entrada M3U
                entry = (
                    f'#EXTINF:-1 group-title="{current_date} {current_competition}" tvg-name="{match_name}",{display_name} ({short_id})\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                )
                entries.append(entry)
    
    return entries

def save_and_history(new_content):
    # Eliminar duplicados manteniendo orden
    seen = set()
    unique_entries = []
    for x in new_content:
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
    if not html: exit(1)
    entries = parse_agenda(html)
    if entries:
        print(f"Éxito: {len(entries)} canales organizados por competición.")
        save_and_history(entries)

if __name__ == "__main__":
    main()
