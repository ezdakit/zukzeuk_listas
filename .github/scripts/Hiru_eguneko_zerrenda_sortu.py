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
    noise = ["Copiar ID", "Reproducir", "Ver Contenido", "Descargar", "FHD", "HD", "SD", "-->", "Links", "Acestream"]
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
    
    # Localizar el área de agenda para evitar menús
    agenda_area = soup.find('div', id='agenda') or soup.body
    
    active_group = "Otros Deportes"
    
    # Analizamos los elementos de la agenda
    for element in agenda_area.find_all(['h3', 'b', 'tr', 'div', 'p']):
        # Evitar bloques masivos (menús ocultos)
        if len(element.get_text()) > 400: continue

        row_str = str(element)
        ids = ace_pattern.findall(row_str)

        # 1. ¿ES UN GRUPO (COMPETICIÓN)? 
        # Si es un encabezado (h3, b) y NO tiene IDs
        if element.name in ['h3', 'b'] and not ids:
            txt = clean_text(element.get_text())
            if 3 < len(txt) < 35 and not any(x in txt.upper() for x in ["TODOS", "CATEGORÍAS", "MENÚ"]):
                active_group = txt
            continue

        # 2. ¿ES UN EVENTO?
        # Debe tener IDs y, para ser evento real de agenda, una HORA
        full_text = element.get_text(" ", strip=True)
        time_match = re.search(r'(\d{1,2}:\d{2})', full_text)
        
        if ids and time_match:
            hora = time_match.group(1)
            # El nombre del partido es lo que sigue a la hora
            name_part = full_text.split(hora)[-1]
            match_name = clean_text(name_part)

            if len(match_name) < 3: 
                match_name = f"Evento {active_group}"

            for aid in list(dict.fromkeys(ids)):
                short_id = aid[:3]
                # Estructura final solicitada
                entry = (
                    f'#EXTINF:-1 group-title="{current_date} {active_group}" tvg-name="{match_name}",{hora} {match_name} ({short_id})\n'
                    f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                )
                entries.append(entry)
                if len(entries) >= 1000: break
    
    return entries

def main():
    html = get_html_content()
    if not html:
        print("Error de conexión.")
        return

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
        
        # Historial
        if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR)
        shutil.copy(OUTPUT_FILE, os.path.join(HISTORY_DIR, f"zz_eventos_{datetime.now().strftime('%H%M%S')}.m3u"))
        
        print(f"Éxito: {len(unique_list)} canales generados correctamente.")
    else:
        print("No se encontraron eventos que cumplan el criterio (Hora + ID).")

if __name__ == "__main__":
    main()
