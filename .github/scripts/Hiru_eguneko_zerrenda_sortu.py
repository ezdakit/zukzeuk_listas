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
    # 1. Eliminar frases de sistema que ensucian la lista
    system_trash = [
        "Enlaces de disponibles", "Copiar ID", "Reproducir", "Ver Contenido", 
        "Descargar", "FHD", "HD", "SD", "NEW ERA", "ELCANO", "-->", "ID", 
        "Links", "Acestream", "Agenda Deportiva", "Grid Lista", "Categorías", "Etiquetas"
    ]
    for trash in system_trash:
        text = text.replace(trash, "")
    
    # 2. Quitar IDs de 40 caracteres
    text = re.sub(r'[a-f0-9]{40}', '', text)
    # 3. Limpiar símbolos y espacios
    text = re.sub(r'\s+', ' ', text).strip(" -:>()")
    return text

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # Empezamos con un grupo genérico por si hay eventos antes del primer título
    current_competition = "Deportes"

    # Buscamos todas las filas de tabla y encabezados
    # El truco es que las competiciones suelen estar en celdas que ocupan toda la fila (colspan)
    for element in soup.find_all(['tr', 'h2', 'h3', 'b']):
        
        # Obtener IDs en este elemento
        html_str = str(element)
        ids = ace_pattern.findall(html_str)
        raw_text = element.get_text(" ", strip=True)

        # CASO A: Es una CABECERA de Competición
        # Si es un texto corto, no tiene IDs y no es menú, es la competición (ej: NCAA)
        if not ids:
            cleaned_comp = clean_text(raw_text)
            if 2 < len(cleaned_comp) < 45 and not any(x in cleaned_comp.upper() for x in ["TODOS", "MENÚ", "AGENDA"]):
                current_competition = cleaned_comp
            continue

        # CASO B: Es una FILA de Evento (Tiene IDs)
        if ids:
            # 1. Extraer Hora
            time_match = re.search(r'(\d{1,2}:\d{2})', raw_text)
            event_time = time_match.group(1) if time_match else ""
            
            # 2. Extraer el Nombre del Partido de forma aislada
            # Intentamos quedarnos solo con lo que hay después de la hora
            if event_time:
                match_name = raw_text.split(event_time)[-1]
            else:
                match_name = raw_text
            
            match_name = clean_text(match_name)
            
            # Si al limpiar se queda vacío o es igual a la competición, poner un genérico
            if len(match_name) < 3:
                match_name = "Evento"

            # 3. Generar entrada por cada ID único
            for aid in list(dict.fromkeys(ids)):
                short_id = aid[:3]
                display_name = f"{event_time} {match_name}".strip()
                # Formato solicitado: group-title="DD-MM Competición"
                group_title = f"{current_date} {current_competition}"

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
            print(f"Éxito: {len(entries)} canales generados.")
        else:
            print("No se encontraron eventos procesables.")
    else:
        print("Error al descargar el contenido.")

if __name__ == "__main__":
    main()
