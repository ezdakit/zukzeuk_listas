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
    # Eliminar basura específica detectada en tu HTML
    noise = ["Copiar ID", "Reproducir", "Ver Contenido", "Descargar", "FHD", "HD", "SD", "NEW ERA", "ELCANO", "Acestream"]
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
    
    # Seleccionamos solo el contenedor principal de la agenda para evitar el menú superior
    # En tu HTML, la agenda suele estar dentro de un div con id 'agenda' o similar
    agenda_container = soup.find('div', {'id': 'agenda'}) or soup.find('main') or soup
    
    current_comp = "Deportes"
    
    # Buscamos bloques de eventos. Tu HTML usa estructuras de filas o tarjetas.
    for element in agenda_container.find_all(['div', 'tr', 'h3', 'b']):
        # 1. TEST DE GRUPO: Identificar competición
        if element.name in ['h3', 'b'] and not ace_pattern.search(str(element)):
            txt = clean_text(element.get_text())
            if 3 < len(txt) < 40 and "TODOS" not in txt.upper():
                current_comp = txt
            continue

        # 2. TEST DE EVENTO: Buscar IDs de Acestream
        row_str = str(element)
        ids = ace_pattern.findall(row_str)
        if not ids: continue

        full_text = element.get_text(" ", strip=True)
        time_match = re.search(r'(\d{1,2}:\d{2})', full_text)
        hora = time_match.group(1) if time_match else ""

        # 3. TEST DE NOMBRE: Evitar que el nombre sea igual al grupo o genérico
        # Extraemos el texto después de la hora
        match_name = full_text.split(hora)[-1] if hora else full_text
        match_name = clean_text(match_name)

        if len(match_name) < 4:
            match_name = f"Evento {current_comp}"

        # 4. TEST DE CANTIDAD: No más de 1000
        if len(entries) >= 1000: break

        for aid in list(dict.fromkeys(ids)):
            short_id = aid[:3]
            group_title = f"{current_date} {current_comp}"
            # Asegurar que el nombre del canal es informativo
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
    
    # VALIDACIÓN ANTES DE GUARDAR
    if entries:
        # Deduplicar preservando orden
        final_list = []
        seen = set()
        for e in entries:
            if e not in seen:
                final_list.append(e)
                seen.add(e)

        # Escribir archivo
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(HEADER_M3U + "\n\n" + "\n\n".join(final_list))
        
        # Historial
        if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR)
        shutil.copy(OUTPUT_FILE, os.path.join(HISTORY_DIR, f"zz_eventos_{datetime.now().strftime('%H%M%S')}.m3u"))
        
        print(f"Resultado: {len(final_list)} eventos procesados. Grupos diferenciados y nombres limpios.")
    else:
        print("No se encontraron eventos. Revisar selectores.")

if __name__ == "__main__":
    main()
