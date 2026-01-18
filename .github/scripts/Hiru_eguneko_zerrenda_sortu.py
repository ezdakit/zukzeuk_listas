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
                # Forzamos UTF-8 y manejamos posibles errores de decodificación
                r.encoding = 'utf-8'
                return r.text
        except: continue
    return None

def clean_event_name(text):
    """Limpia el ruido del nombre del evento y el grupo"""
    if not text: return ""
    # Eliminar términos técnicos y de navegación
    noise = [
        "FHD", "HD", "SD", "NEW ERA", "ELCANO", "SPORT TV", "VI FHD", "II FHD", "III FHD", 
        "IV FHD", "V FHD", "NEW LOOP", "Copiar", "ID", "Reproducir", "Ver Contenido", 
        "Descargar", "Enlaces de Acestream disponibles", "Lista Plana", "Lista KODI", 
        "Lista Reproductor IPTV", "-->", "-->"
    ]
    for word in noise:
        text = text.replace(word, "")
    
    # Quitar hashes de 40 caracteres (IDs)
    text = re.sub(r'[a-f0-9]{40}', '', text)
    # Quitar espacios extra y guiones
    text = re.sub(r'\s+', ' ', text)
    return text.strip(" -:>")

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # Intentamos identificar la competición actual
    current_competition = "Eventos"

    # Procesamos filas de tabla o bloques de div que suelen contener la info
    for element in soup.find_all(['tr', 'div']):
        # Evitar procesar el mismo texto varias veces si el div contiene el tr
        if element.name == 'div' and element.find('tr'):
            continue
            
        raw_text = element.get_text(" ", strip=True)
        html_str = str(element)
        ids = ace_pattern.findall(html_str)

        # 1. Si no hay IDs, puede ser un cambio de sección (Competición)
        if not ids:
            clean_t = clean_event_name(raw_text)
            if 3 < len(clean_t) < 50 and not any(x in clean_t for x in ["TODOS", "Categorías"]):
                current_competition = clean_t
            continue

        # 2. Si hay IDs, extraemos la información del evento
        # Buscar hora (formato 00:00)
        time_match = re.search(r'(\d{1,2}:\d{2})', raw_text)
        event_time = time_match.group(1) if time_match else ""
        
        # El nombre del evento es el texto de la fila limpiando el ruido, la hora y la competición
        match_name = clean_event_name(raw_text.replace(event_time, "").replace(current_competition, ""))
        
        if not match_name or len(match_name) < 3:
            match_name = "Evento"

        # Añadir cada ID único encontrado en esta fila
        seen_ids_in_row = []
        for aid in ids:
            if aid not in seen_ids_in_row:
                seen_ids_in_row.append(aid)
                short_id = aid[:3]
                
                # Nombre a mostrar: "Hora - Nombre del Partido (ID)"
                display_name = f"{event_time} {match_name}".strip()
                group_name = f"{current_date} {current_competition}".strip()

                entry = (
                    f'#EXTINF:-1 group-title="{group_name}" tvg-name="{match_name}",{display_name} ({short_id})\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                )
                entries.append(entry)
    
    return entries

def save_and_history(new_content):
    # Eliminar duplicados manteniendo el orden
    final_entries = []
    seen = set()
    for item in new_content:
        if item not in seen:
            final_entries.append(item)
            seen.add(item)
            
    full_content = HEADER_M3U + "\n\n" + "\n\n".join(final_entries)
    
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
        print("Error: No se pudo obtener el HTML.")
        return
    
    entries = parse_agenda(html)
    if entries:
        save_and_history(entries)
        print(f"Éxito: {len(entries)} eventos procesados.")
    else:
        print("No se encontraron eventos nuevos.")

if __name__ == "__main__":
    main()
