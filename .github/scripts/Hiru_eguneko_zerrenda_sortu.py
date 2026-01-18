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
    # Basura específica que hemos visto en tu HTML
    noise = [
        "Copiar ID", "Reproducir", "Ver Contenido", "Descargar", "FHD", "HD", "SD", 
        "NEW ERA", "ELCANO", "SPORT TV", "-->", "Links", "Acestream", "Grid Lista",
        "Categorías:", "Etiquetas:", "TODOS", "NEW LOOP"
    ]
    for n in noise:
        text = text.replace(n, "")
    text = re.sub(r'[a-f0-9]{40}', '', text) # Quitar IDs
    text = re.sub(r'\s+', ' ', text).strip(" -:>()")
    return text

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # 1. EVITAR EL MENÚ: Buscamos solo el contenedor de la "Agenda Deportiva"
    # Según tu HTML, los eventos están en una sección específica
    agenda_section = soup.find('div', id='agenda') or soup.find('div', class_='tab-content')
    
    # Si no encontramos el contenedor, usamos el cuerpo pero con filtros estrictos
    search_area = agenda_section if agenda_section else soup.body

    current_comp = "Deportes"
    
    # Buscamos todas las filas que parecen eventos
    # Filtramos por las que tienen un ID de Acestream
    for element in search_area.find_all(['tr', 'div', 'h3']):
        row_str = str(element)
        ids = ace_pattern.findall(row_str)
        
        # Si no hay ID, podría ser un título de competición (NCAA, 1RFEF...)
        if not ids:
            txt = clean_text(element.get_text())
            # Solo aceptamos como grupo si es un texto corto y no es del menú
            if 3 < len(txt) < 30 and not any(x in txt.upper() for x in ["CATEGORÍAS", "ETIQUETAS", "GRID"]):
                current_comp = txt
            continue

        # Si hay IDs, es un evento. Validamos que no sea el menú gigante.
        full_text = element.get_text(" ", strip=True)
        if len(full_text) > 300: continue # El menú gigante tiene cientos de letras, lo saltamos

        # Buscamos la hora HH:MM
        time_match = re.search(r'(\d{1,2}:\d{2})', full_text)
        hora = time_match.group(1) if time_match else ""
        
        # Extraer nombre del partido (lo que queda después de la hora)
        match_name = full_text.split(hora)[-1] if hora else full_text
        match_name = clean_text(match_name)
        
        # Si no hay hora ni nombre real, es basura técnica
        if not hora and (len(match_name) < 5 or "Canal" in match_name):
            continue

        # REGLA DE SEGURIDAD: Máximo 1000
        if len(entries) >= 1000: break

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
        # Eliminar duplicados exactos
        final_list = []
        seen = set()
        for e in entries:
            if e not in seen:
                final_list.append(e)
                seen.add(e)

        # Escribir con codificación UTF-8 para las tildes
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(HEADER_M3U + "\n\n" + "\n\n".join(final_list))
        
        # Guardar en historial
        if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR)
        shutil.copy(OUTPUT_FILE, os.path.join(HISTORY_DIR, f"zz_eventos_{datetime.now().strftime('%H%M%S')}.m3u"))
        print(f"Éxito: {len(final_list)} eventos guardados.")
    else:
        print("No se encontraron eventos válidos en la agenda.")

if __name__ == "__main__":
    main()
