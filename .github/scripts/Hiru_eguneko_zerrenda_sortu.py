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
    # Basura detectada en los nombres
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
    
    # 1. Filtro de zona: Solo la agenda real
    agenda_area = soup.find('div', id='agenda') or soup.body
    
    # Variable de estado para mantener la competición
    active_competition = "Deportes"

    # Iteramos por elementos clave para mantener el orden
    for element in agenda_area.find_all(['h3', 'b', 'tr', 'div']):
        # Ignorar el menú gigante (basado en longitud)
        if len(element.get_text()) > 500: continue

        row_str = str(element)
        ids = ace_pattern.findall(row_str)

        # CASO A: Es un título de competición (No tiene IDs y es texto corto)
        if not ids:
            candidate = clean_text(element.get_text())
            if 3 < len(candidate) < 35 and not any(x in candidate.upper() for x in ["TODOS", "CATEGORÍAS", "MENÚ"]):
                active_competition = candidate
            continue

        # CASO B: Es un evento (Tiene IDs)
        full_text = element.get_text(" ", strip=True)
        time_match = re.search(r'(\d{1,2}:\d{2})', full_text)
        
        # Si tiene ID pero no tiene hora, suele ser un canal del menú, lo saltamos
        if not time_match: continue
        
        hora = time_match.group(1)
        # El nombre del partido es lo que viene después de la hora
        match_name = clean_text(full_text.split(hora)[-1])

        if len(match_name) < 3:
            match_name = f"Evento {active_competition}"

        # Evitar duplicados de IDs en la misma fila
        for aid in list(dict.fromkeys(ids)):
            short_id = aid[:3]
            # ESTRUCTURA SOLICITADA:
            # group-title = Fecha + Competición
            # tvg-name = Nombre del Partido
            group_title = f"{current_date} {active_competition}"
            
            entry = (
                f'#EXTINF:-1 group-title="{group_title}" tvg-name="{match_name}",{hora} {match_name} ({short_id})\n'
                f'http://127.0.0.1:6878/ace/getstream?id={aid}'
            )
            entries.append(entry)
            
            if len(entries) >= 1000: break
            
    return entries

def main():
    html = get_html_content()
    if not html: return

    entries = parse_agenda(html)
    
    if entries:
        # Deduplicar preservando orden
        final = []
        seen = set()
        for e in entries:
            if e not in seen:
                final.append(e)
                seen.add(e)

        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(HEADER_M3U + "\n\n" + "\n\n".join(final))
        
        # Historial
        if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR)
        shutil.copy(OUTPUT_FILE, os.path.join(HISTORY_DIR, f"zz_eventos_{datetime.now().strftime('%H%M%S')}.m3u"))
        print(f"Éxito: {len(final)} canales. Estructura: {active_competition} > {match_name}")
    else:
        print("No se encontraron eventos con el formato Hora + ID.")

if __name__ == "__main__":
    main()
