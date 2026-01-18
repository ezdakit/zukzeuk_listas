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

def clean_text(text, competition=""):
    """Limpia el ruido y evita repetir la competición en el nombre del partido"""
    if not text: return ""
    # Basura técnica
    noise = ["FHD", "HD", "SD", "NEW ERA", "ELCANO", "SPORT TV", "VI FHD", "II FHD", "III FHD", "IV FHD", "V FHD", "Copiar ID", "Reproducir", "Ver Contenido", "-->", "ID"]
    for n in noise:
        text = text.replace(n, "")
    
    # Quitar el nombre de la competición si ya está en el nombre del partido
    if competition and competition.lower() in text.lower():
        text = re.sub(re.escape(competition), '', text, flags=re.IGNORECASE)
    
    # Quitar hashes, espacios extra y caracteres raros
    text = re.sub(r'[a-f0-9]{40}', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip(" -:>")

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    current_comp = "Deportes"
    
    # Buscamos todos los elementos relevantes
    # En estas webs, las competiciones suelen ser h2/h3 o b, y los partidos están en tr o divs
    for el in soup.find_all(['h1', 'h2', 'h3', 'b', 'tr', 'div']):
        
        # 1. ¿Es un posible título de competición?
        if el.name in ['h1', 'h2', 'h3', 'b'] and not ace_pattern.search(str(el)):
            txt = el.get_text(strip=True)
            if 3 < len(txt) < 40 and not any(x in txt for x in ["Categorías", "Etiquetas", "TODOS"]):
                current_comp = clean_text(txt)
            continue

        # 2. ¿Contiene enlaces de Acestream?
        ids = ace_pattern.findall(str(el))
        if ids:
            # IMPORTANTE: Cogemos el texto de TODO el contenedor (la fila), no solo del botón
            # Si el elemento es un 'div' pequeño o un 'td', intentamos subir al 'tr' o contenedor padre
            container = el.find_parent('tr') or el
            full_row_text = container.get_text(" ", strip=True)
            
            # Extraer hora (HH:MM)
            time_match = re.search(r'(\d{1,2}:\d{2})', full_row_text)
            event_time = time_match.group(1) if time_match else ""
            
            # Limpiar el nombre del partido
            # Quitamos la hora para que no se repita en el tvg-name
            match_name = clean_text(full_row_text.replace(event_time, ""), current_comp)
            
            if not match_name or len(match_name) < 3:
                match_name = "Evento"

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
    # Eliminar duplicados exactos
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
            print(f"Lista generada: {len(entries)} eventos.")
        else:
            print("No se encontraron eventos.")
    else:
        print("Error al descargar el contenido.")

if __name__ == "__main__":
    main()
