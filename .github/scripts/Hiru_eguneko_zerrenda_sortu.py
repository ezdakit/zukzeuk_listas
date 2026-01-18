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
            print(f"Probando: {gw}...")
            r = requests.get(f"{gw}{IPNS_KEY}{PATH_PARAMS}", headers={'User-Agent': ua.random}, timeout=40)
            if r.status_code == 200 and len(r.text) > 1000: return r.text
        except: continue
    return None

def parse_agenda(html):
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # Palabras a eliminar de los títulos para que queden limpios
    noise = ["Copiar ID", "Reproducir", "-->", "NEW ERA", "ELCANO", "SPORT TV", "VI FHD", "FHD", "HD", "SD"]

    # Buscamos elementos que suelen contener los canales
    soup = BeautifulSoup(html, 'lxml')
    
    # Intentamos buscar por líneas de texto que contengan un hash de Acestream
    # Esto evita capturar el "bloque" gigante del menú
    for line in soup.get_text("\n").split("\n"):
        line = line.strip()
        ids = ace_pattern.findall(line)
        
        if ids:
            # Si la línea es muy larga (como el error anterior), la procesamos con cuidado
            if len(line) > 200:
                # Intentamos sacar el nombre antes del ID
                clean_name = line.split(ids[0])[0].strip()
            else:
                clean_name = line
            
            # Limpieza profunda del nombre
            for word in noise:
                clean_name = clean_name.replace(word, "")
            
            # Quitar la propia ID del nombre y símbolos raros
            clean_name = re.sub(r'[a-f0-9]{40}', '', clean_name)
            clean_name = re.sub(r'\s+', ' ', clean_name).strip(" -:>")
            
            if not clean_name: clean_name = "Canal Evento"

            for aid in list(dict.fromkeys(ids)):
                # Intentamos extraer una hora si existe
                time_match = re.search(r'(\d{1,2}:\d{2})', line)
                event_time = time_match.group(1) if time_match else ""
                
                name_final = f"{event_time} {clean_name}".strip()
                short_id = aid[:3]
                
                entry = (
                    f'#EXTINF:-1 group-title="{current_date} Deportes" tvg-name="{name_final}",{name_final} ({short_id})\n'
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
    
    # Solo guardar si hay cambios reales
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            if f.read().strip() == full_content.strip():
                print("Sin cambios nuevos.")
                return

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
        print(f"Generadas {len(entries)} entradas limpias.")
        save_and_history(entries)

if __name__ == "__main__":
    main()
