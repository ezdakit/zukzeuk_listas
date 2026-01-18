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

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # 1. LOCALIZAR LAS TABLAS: La agenda real siempre está en tablas <table>
    # Esto ignora automáticamente el menú de arriba y los laterales
    tables = soup.find_all('table')
    
    for table in tables:
        # Buscamos el título de la competición justo antes de la tabla
        # Normalmente es un h2, h3 o un b que está encima
        prev = table.find_previous(['h2', 'h3', 'b', 'strong'])
        current_comp = prev.get_text(strip=True) if prev else "Deportes"
        
        # Limpiar nombre de competición (evitar menús)
        if len(current_comp) > 40 or "TODOS" in current_comp.upper():
            current_comp = "Evento"

        rows = table.find_all('tr')
        for row in rows:
            text_row = row.get_text(" ", strip=True)
            ids = ace_pattern.findall(str(row))
            
            if ids:
                # Buscar hora HH:MM
                time_match = re.search(r'(\d{1,2}:\d{2})', text_row)
                hora = time_match.group(1) if time_match else ""
                
                # EL NOMBRE DEL PARTIDO:
                # Es el texto que NO es la hora y NO son los botones de ID
                match_name = text_row.replace(hora, "")
                # Limpieza rápida de ruidos comunes
                for noise in ["Copiar ID", "Reproducir", "Ver", "Descargar", "FHD", "HD", "SD"]:
                    match_name = match_name.replace(noise, "")
                
                match_name = re.sub(r'\s+', ' ', match_name).strip(" -:>()")

                # Si el nombre queda vacío, usamos el título de la competición
                if len(match_name) < 3: match_name = current_comp

                for aid in list(dict.fromkeys(ids)):
                    short_id = aid[:3]
                    group_title = f"{current_date} {current_comp}"
                    display_name = f"{hora} {match_name}".strip()

                    entry = (
                        f'#EXTINF:-1 group-title="{group_title}" tvg-name="{match_name}",{display_name} ({short_id})\n'
                        f'http://127.0.0.1:6878/ace/getstream?id={aid}'
                    )
                    entries.append(entry)
                    
    return entries

def main():
    html = get_html_content()
    if not html: return

    entries = parse_agenda(html)
    
    if entries:
        # Deduplicar
        unique = []
        seen = set()
        for e in entries:
            if e not in seen:
                unique.append(e)
                seen.add(e)

        content = HEADER_M3U + "\n\n" + "\n\n".join(unique)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        
        if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR)
        shutil.copy(OUTPUT_FILE, os.path.join(HISTORY_DIR, f"zz_eventos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.m3u"))
        print(f"Éxito: {len(unique)} canales.")
    else:
        # Si fallan las tablas, intentamos un modo desesperado (todo lo que tenga ID)
        print("Aviso: No se encontraron tablas, usando modo bypass...")
        # (Aquí podrías poner un fallback, pero probemos primero con el filtro de tablas)

if __name__ == "__main__":
    main()
