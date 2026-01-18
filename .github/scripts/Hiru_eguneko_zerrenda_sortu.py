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
                r.encoding = 'utf-8' # Forzamos UTF-8 para corregir "FEDERACIÓN"
                return r.text
        except: continue
    return None

def clean_label(text):
    """Limpia el nombre del partido de ruidos y botones"""
    if not text: return ""
    # Eliminar términos de sistema y botones
    trash = [
        "Enlaces de disponibles", "Copiar ID", "Reproducir", "Ver Contenido", 
        "Descargar", "FHD", "HD", "SD", "NEW ERA", "ELCANO", "-->", "ID", 
        "Links", "Acestream", "Grid Lista", "Categorías", "Etiquetas", "()"
    ]
    for t in trash:
        text = text.replace(t, "")
    
    # Eliminar hashes de 40 caracteres
    text = re.sub(r'[a-f0-9]{40}', '', text)
    # Limpiar espacios múltiples y símbolos
    text = re.sub(r'\s+', ' ', text).strip(" -:>()")
    return text

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # Grupo por defecto
    current_comp = "Otros Deportes"

    # Buscamos todas las filas (tr) que son donde están los datos reales
    # y los encabezados (h2, h3, b) para las competiciones
    for row in soup.find_all(['tr', 'h2', 'h3', 'b']):
        row_str = str(row)
        ids = ace_pattern.findall(row_str)
        text = row.get_text(" ", strip=True)

        # 1. Identificar COMPETICIÓN (Si no hay IDs y el texto es corto/relevante)
        if not ids:
            clean_t = clean_label(text)
            if 2 < len(clean_t) < 40 and not any(x in clean_t.upper() for x in ["TODOS", "MENÚ", "AGENDA"]):
                current_comp = clean_t
            continue

        # 2. Identificar EVENTO (Si hay IDs)
        if ids:
            # Buscamos la hora (HH:MM)
            time_match = re.search(r'(\d{1,2}:\d{2})', text)
            event_time = time_match.group(1) if time_match else ""
            
            # El nombre del partido es lo que queda tras la hora
            # pero antes de que empiecen los IDs de Acestrem
            if event_time:
                # Separamos por la hora y nos quedamos con la parte derecha
                parts = text.split(event_time)
                match_name = parts[-1] if len(parts) > 1 else text
            else:
                match_name = text

            match_name = clean_label(match_name)
            
            # Si el nombre capturado es "Evento" o similar, intentamos usar la competición
            if len(match_name) < 3 or match_name.lower() == "evento":
                match_name = current_comp

            # Generar una línea por cada ID único
            unique_ids = []
            for aid in ids:
                if aid not in unique_ids:
                    unique_ids.append(aid)
                    short_id = aid[:3]
                    
                    # Formato final solicitado
                    group_title = f"{current_date} {current_comp}"
                    display_name = f"{event_time} {match_name}".strip()

                    entry = (
                        f'#EXTINF:-1 group-title="{group_title}" tvg-name="{match_name}",{display_name} ({short_id})\n'
                        f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                    )
                    entries.append(entry)
                    
    return entries

def save_and_history(entries):
    # Eliminar duplicados manteniendo el orden
    final = []
    seen = set()
    for e in entries:
        if e not in seen:
            final.append(e)
            seen.add(e)

    content = HEADER_M3U + "\n\n" + "\n\n".join(final)
    
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
            print(f"Éxito: {len(entries)} canales extraídos correctamente.")
        else:
            print("No se encontraron eventos en esta ejecución.")
    else:
        print("Error: No se pudo conectar con el Gateway.")

if __name__ == "__main__":
    main()
