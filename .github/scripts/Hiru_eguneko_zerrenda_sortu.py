import os, requests, re, shutil
from bs4 import BeautifulSoup
from datetime import datetime
from fake_useragent import UserAgent

# --- KONFIGURAZIOA ---
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
            r = requests.get(url, headers={'User-Agent': ua.random}, timeout=30)
            if r.status_code == 200:
                r.encoding = 'utf-8'
                return r.text
        except: continue
    return None

def clean_text(text):
    if not text: return ""
    # Kendu soberan dagoen guztia
    noise = ["Copiar ID", "Reproducir", "Ver Contenido", "Descargar", "FHD", "HD", "SD", "-->", "ID", "Acestream", "Enlaces de disponibles"]
    for n in noise:
        text = text.replace(n, "")
    # Kendu hash-ak
    text = re.sub(r'[a-f0-9]{40}', '', text)
    # Garbitu zuriuneak eta karaktere arraroak
    text = re.sub(r'\s+', ' ', text).strip(" -:>()")
    return text

def parse_agenda(html):
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    current_comp = "Kirol Ekitaldiak"
    
    # Bilatu eduki guztia lerroz lerro (tr, div edo p)
    for element in soup.find_all(['tr', 'h2', 'h3', 'b', 'div']):
        raw_text = element.get_text(" ", strip=True)
        ids = ace_pattern.findall(str(element))

        # 1. Kategoria edo Txapelketa (IDrik gabe eta laburra)
        if not ids:
            cleaned = clean_text(raw_text)
            if 3 < len(cleaned) < 40 and "TODOS" not in cleaned.upper():
                current_comp = cleaned
            continue

        # 2. Partida (IDak aurkitu badira)
        # Bilatu ordua (hautazkoa orain, ez badago ez dugu baztertuko)
        time_match = re.search(r'(\d{1,2}:\d{2})', raw_text)
        hora = time_match.group(1) if time_match else ""
        
        # Izena garbitu: orduaren ostean dagoena edo testu osoa
        if hora:
            match_name = raw_text.split(hora)[-1]
        else:
            match_name = raw_text
            
        match_name = clean_text(match_name)

        if len(match_name) < 2:
            match_name = current_comp

        # Gehitu aurkitutako ID bakoitza
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

def save_and_history(entries):
    if not entries: return
    # Kendu bikoiztuak
    unique_entries = []
    seen = set()
    for e in entries:
        if e not in seen:
            unique_entries.append(e)
            seen.add(e)

    full_content = HEADER_M3U + "\n\n" + "\n\n".join(unique_entries)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy(OUTPUT_FILE, os.path.join(HISTORY_DIR, f"zz_eventos_{ts}.m3u"))

def main():
    html = get_html_content()
    if not html:
        print("Akatsa: Ezin izan da webgunera konektatu.")
        return

    entries = parse_agenda(html)
    
    if entries:
        save_and_history(entries)
        print(f"Egina! {len(entries)} kanal sortu dira.")
    else:
        # Debug: orrialdearen zati bat erakutsi IDak dauden ikusteko
        print("Ez da partidarik aurkitu. Orrialdeak ez du Acestream IDrik (40 karaktere).")

if __name__ == "__main__":
    main()
