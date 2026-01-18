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
                r.encoding = 'utf-8' # Forzado de tildes
                return r.text
        except: continue
    return None

def clean_text(text, remove_list):
    """Limpia el texto de etiquetas y basura"""
    # Eliminar términos de la lista
    for item in remove_list:
        if item:
            text = text.replace(item, "")
    
    # Limpieza de patrones comunes de la web
    text = re.sub(r'-->|ID|Copiar|Reproducir|Etiquetas:|Categorías:', '', text)
    # Quitar hashes de 40 caracteres
    text = re.sub(r'[a-f0-9]{40}', '', text)
    # Quitar espacios múltiples y guiones sueltos
    text = re.sub(r'\s+', ' ', text).strip(" -:>")
    return text

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # Lista de ruido para limpiar nombres
    noise = ["FHD", "HD", "SD", "NEW ERA", "ELCANO", "SPORT TV", "VI FHD", "II FHD", "III FHD", "IV FHD", "V FHD", "NEW LOOP"]
    
    current_competition = "Otros"

    # Buscamos elementos en el cuerpo del documento
    # Buscamos filas de tabla o contenedores de bloque
    for element in soup.find_all(['tr', 'div', 'h2', 'h3', 'b']):
        
        # Ignorar elementos que son hijos de otros ya procesados para no duplicar
        if element.name == 'div' and element.find(['tr', 'h2', 'h3']):
            continue

        raw_text = element.get_text(" ", strip=True)
        html_str = str(element)
        ids = ace_pattern.findall(html_str)
        
        # 1. ¿Es una cabecera de competición?
        if not ids:
            # Si el texto es corto y parece un título
            if 2 < len(raw_text) < 60 and not any(x in raw_text for x in ["TODOS", "F1", "Canal"]):
                # Si no tiene números de canal, probablemente es la competición (ej: NCAA, LA LIGA)
                potencial_comp = clean_text(raw_text, noise)
                if potencial_comp:
                    current_competition = potencial_comp
            continue

        # 2. Si tiene IDs, es un evento (un partido o canal)
        # Extraer hora (HH:MM)
        time_match = re.search(r'(\d{1,2}:\d{2})', raw_text)
        event_time = time_match.group(1) if time_match else ""
        
        # Limpiar el nombre del partido
        # Quitamos la hora y el nombre de la competición del título del partido para no repetir
        match_name = clean_text(raw_text, noise + [event_time, current_competition])
        
        # Si después de limpiar no queda nada, le ponemos un genérico
        if len(match_name) < 3: 
            match_name = "Evento Deportivo"

        # Procesar cada ID encontrado en esta sección
        unique_ids = []
        for aid in ids:
            if aid not in unique_ids:
                unique_ids.append(aid)
                
                short_id = aid[:3]
                display_name = f"{event_time} {match_name}".strip()
                
                # Limpiar el nombre del grupo
                group_clean = f"{current_date} {current_competition}".strip()

                entry = (
                    f'#EXTINF:-1 group-title="{group_clean}" tvg-name="{match_name}",{display_name} ({short_id})\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                )
                entries.append(entry)
    
    return entries

def save_and_history(new_content):
    # Eliminar duplicados manteniendo orden (Sin usar walrus operator)
    seen = set()
    unique_entries = []
    for entry in new_content:
        if entry not in seen:
            unique_entries.append(entry)
            seen.add(entry)
            
    full_content = HEADER_M3U + "\n\n" + "\n\n".join(unique_entries)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    if not os.path.exists(HISTORY_DIR):
        os.makedirs(HISTORY_DIR)
        
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy(OUTPUT_FILE, os.path.join(HISTORY_DIR, f"zz_eventos_{ts}.m3u"))
    
    # Mantener historial
    h_files = sorted([os.path.join(HISTORY_DIR, f) for f in os.listdir(HISTORY_DIR)], key=os.path.getmtime)
    while len(h_files) > MAX_HISTORY:
        os.remove(h_files.pop(0))

def main():
    html = get_html_content()
    if not html: 
        print("Error: No se pudo obtener el HTML.")
        return
    
    entries = parse_agenda(html)
    if entries:
        print(f"Éxito: {len(entries)} canales procesados.")
        save_and_history(entries)
    else:
        print("No se encontraron eventos.")

if __name__ == "__main__":
    main()
