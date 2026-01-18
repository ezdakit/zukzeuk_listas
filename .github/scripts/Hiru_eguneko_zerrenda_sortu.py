import os, requests, re, shutil
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
            r = requests.get(f"{gw}{IPNS_KEY}{PATH_PARAMS}", headers={'User-Agent': ua.random}, timeout=30)
            if r.status_code == 200:
                r.encoding = 'utf-8'
                return r.text
        except: continue
    return None

def clean_text(text):
    if not text: return ""
    # Kendu soberan dagoen testu teknikoa
    noise = ["Copiar ID", "Reproducir", "Ver Contenido", "Descargar", "FHD", "HD", "SD", "-->", "ID", "Acestream"]
    for n in noise:
        text = text.replace(n, "")
    # Kendu Acestream hash-ak (40 karaktere)
    text = re.sub(r'[a-f0-9]{40}', '', text)
    # Garbitu zuriuneak
    text = re.sub(r'\s+', ' ', text).strip(" -:>()")
    return text

def parse_content(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    current_date = datetime.now().strftime("%d-%m")
    ace_pattern = re.compile(r'[a-f0-9]{40}')
    
    # Bilatu orrialdeko lerro guztiak (tr)
    rows = soup.find_all('tr')
    
    # Orrialdean taularik ez badago (oso arraroa), saiatu div-ekin
    if not rows:
        rows = soup.find_all('div')

    current_comp = "Kirolak"

    for row in rows:
        text = row.get_text(" ", strip=True)
        html_row = str(row)
        ids = ace_pattern.findall(html_row)

        # 1. Izenburua den detektatu (ID-rik gabe eta testu laburra)
        if not ids:
            cleaned = clean_text(text)
            if 3 < len(cleaned) < 35 and "TODOS" not in cleaned.upper():
                current_comp = cleaned
            continue

        # 2. Partida den detektatu (Ordua + IDak)
        time_match = re.search(r'(\d{1,2}:\d{2})', text)
        if ids and time_match:
            hora = time_match.group(1)
            # Partidaren izena orduaren ostean dagoena da
            match_name = text.split(hora)[-1]
            match_name = clean_text(match_name)
            
            if not match_name or len(match_name) < 3:
                match_name = "Ekitaldia"

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
    if not html:
        print("Ezin izan da HTMLa eskuratu.")
        return

    entries = parse_content(html)
    
    if entries:
        # Kendu bikoiztuak
        unique_entries = []
        seen = set()
        for e in entries:
            if e not in seen:
                unique_entries.append(e)
                seen.add(e)

        content = HEADER_M3U + "\n\n" + "\n\n".join(unique_entries)
        
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Historiala kudeatu
        if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(OUTPUT_FILE, os.path.join(HISTORY_DIR, f"zz_eventos_{ts}.m3u"))
        
        print(f"Egina! {len(unique_entries)} partida aurkitu dira.")
    else:
        print("Ez da partidarik aurkitu ordu formatuarekin. Egiaztatu IPNS gakoa.")

if __name__ == "__main__":
    main()
