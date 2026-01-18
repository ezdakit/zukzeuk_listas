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

def is_garbage(text):
    """Detecta si el texto es parte de las instrucciones de la web y no un partido"""
    garbage_keywords = [
        "reproductores", "VLC", "OTT", "Kodi", "plugin", "acestream://", 
        "fuente M3U", "software IPTV", "Copiar", "instrucciones", "ID_ACESTREAM",
        "Enlaces de disponibles", "Grid Lista", "Categorías"
    ]
    return any(word.lower() in text.lower() for word in garbage_keywords)

def clean_text(text):
    if not text: return ""
    # Ruido visual
    noise = ["FHD", "HD", "SD", "-->", "Links", "Acestream", "NEW ERA", "ELCANO"]
    for n in noise:
        text = text.replace(n, "")
    text = re.sub(r'[a-f0-9]{40}', '', text)
    text = re.sub(r'\s+', ' ', text).strip(" -:>()")
    return text

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # Solo buscamos en la zona de la agenda
    agenda_area = soup.find('div', id='agenda') or soup.body
    
    active_group = "Otros"

    for element in agenda_area.find_all(['h3', 'b', 'tr', 'div']):
        # Evitar bloques de texto masivos
        if len(element.get_text()) > 350: continue

        row_str = str(element)
        ids = ace_pattern.findall(row_str)

        # 1. ACTUALIZAR GRUPO (Competición)
        if element.name in ['h3', 'b'] and not ids:
            txt = clean_text(element.get_text())
            if 3 < len(txt) < 30 and not is_garbage(txt):
                active_group = txt
            continue

        # 2. PROCESAR EVENTO
        full_text = element.get_text(" ", strip=True)
        time_match = re.search(r'(\d{1,2}:\d{2})', full_text)
        
        # Un evento válido DEBE tener Hora e ID, y NO ser basura técnica
        if ids and time_match:
            hora = time_match.group(1)
            raw_name = full_text.split(hora)[-1]
            match_name = clean_text(raw_name)

            if is_garbage(match_name) or len(match_name) < 4:
                continue

            for aid in list(dict.fromkeys(ids)):
                short_id = aid[:3]
                entry = (
                    f'#EXTINF:-1 group-title="{current_date} {active_group}" tvg-name="{match_name}",{hora} {match_name} ({short_id})\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                )
                entries.append(entry)
                if len(entries) >= 1000: break
    
    return entries

def main():
    html = get_html_content()
    if not html: return

    final_entries = parse_agenda(html)
    
    if final_entries:
        # Deduplicar
        unique_list = []
        seen = set()
        for e in final_entries:
            if e not in seen:
                unique_list.append(e)
                seen.add(e)

        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(HEADER_M3U + "\n\n" + "\n\n".join(unique_list))
        
        if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR)
        shutil.copy(OUTPUT_FILE, os.path.join(HISTORY_DIR, f"zz_eventos_{datetime.now().strftime('%H%M%S')}.m3u"))
        print(f"Éxito: {len(unique_list)} canales limpios.")
    else:
        print("No se encontraron eventos válidos.")

if __name__ == "__main__":
    main()
