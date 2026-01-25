import os
import sys
import re
import csv
import time
import requests
import cloudscraper
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime

# ============================================================================================
# CONFIGURACIÓN Y ENTORNO
# ============================================================================================

# Detectar modo testing desde argumentos
TEST_MODE = "--testing" in sys.argv
SUFFIX = "_testing" if TEST_MODE else ""

# URLs Externas (Siempre producción)
URL_ELCANO = "https://raw.githubusercontent.com/davidmuma/Canales_Eldelbar/main/M3U/elcano.m3u"
URL_NEW_ERA = "https://raw.githubusercontent.com/davidmuma/Canales_Eldelbar/main/M3U/new_era.m3u"
URL_AGENDA = "https://guia-deportiva.com/"  # URL Base para el scraping

# Definición de Rutas (Usamos cwd para asegurar que funcione desde la raíz del repo en Actions)
BASE_DIR = Path.cwd()
DIR_CANALES = BASE_DIR / "canales"

print(f"######################################################################")
print(f"### ZukZeuk SYSTEM: {'MODO TESTING 🛠️' if TEST_MODE else 'PRODUCCIÓN 🚀'}")
print(f"### Directorio Base: {BASE_DIR}")
print(f"### Sufijo de archivos: '{SUFFIX}'")
print(f"######################################################################\n")

# ============================================================================================
# GESTIÓN DE RUTAS
# ============================================================================================

def get_path(filename, is_input_local=False):
    """
    Retorna la ruta completa del archivo con el sufijo _testing si corresponde.
    Si es un input local crítico y estamos en testing, falla si no existe.
    """
    path_obj = Path(filename)
    
    # Si la ruta ya es absoluta o relativa compleja, respetarla. Si no, añadir al BASE_DIR
    if path_obj.is_absolute():
        final_path = path_obj.parent / f"{path_obj.stem}{SUFFIX}{path_obj.suffix}"
    else:
        # Asumimos que si no tiene path, va en la raíz, salvo que se especifique carpeta en filename
        final_path = BASE_DIR / path_obj.parent / f"{path_obj.stem}{SUFFIX}{path_obj.suffix}"

    # Verificación estricta para inputs locales en testing
    if is_input_local and TEST_MODE:
        if not final_path.exists():
            print(f"❌ [CRITICAL] Falta archivo de input en modo testing: {final_path}")
            sys.exit(1)
            
    return final_path

# Archivos Salida M3U
FILE_ELCANO_OUT = get_path("elcano.m3u")
FILE_NEW_ERA_OUT = get_path("new_era.m3u")
FILE_EZDAKIT = get_path("ezdakit.m3u")
FILE_EZDAKIT_EVENTOS = get_path("ezdakit_eventos.m3u")

# Archivos CSV Locales
FILE_LISTADO_CANALES = get_path(DIR_CANALES / "listado_canales.csv", is_input_local=True)
FILE_LISTA_NEGRA = get_path(DIR_CANALES / "lista_negra.csv", is_input_local=True)
FILE_CORRESPONDENCIAS = get_path(DIR_CANALES / "correspondencias.csv")
FILE_EVENTOS_CSV = get_path(DIR_CANALES / "eventos_canales.csv")

# ============================================================================================
# HERRAMIENTAS DE LIMPIEZA
# ============================================================================================

def clean_name(name):
    """Limpieza agresiva de nombres según Reglas de Oro."""
    if not name: return ""
    
    # 1. Eliminar sufijos de idioma y basura visual
    name = re.sub(r'\((ES|EN|FR|IT|DE|RU|PT|LAT)\)', '', name, flags=re.IGNORECASE)
    name = name.replace('|', '').replace('vip', '').replace('( )', '')
    
    # 2. Eliminar Calidades y Códecs
    calidades = r'\b(1080p|FHD|4K|UHD|SD|HD|HEVC|H\.265|60fps)\b'
    name = re.sub(calidades, '', name, flags=re.IGNORECASE)
    
    # 3. Eliminar IDs de Acestream al final (Hash de 40 chars) o formatos "-->"
    name = re.sub(r'[a-f0-9]{40}$', '', name)
    name = re.sub(r'\s[a-f0-9]{3,10}\s?-->.*$', '', name)
    
    # 4. [REGLA CRÍTICA] Eliminar palabra exacta "BAR"
    name = re.sub(r'\bBAR\b', '', name) 

    # Limpieza final de espacios
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def normalize_text(text):
    """Normaliza texto para comparaciones (mayúsculas, sin tildes)."""
    if not text: return ""
    replacements = (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n"))
    text = text.lower().strip()
    for a, b in replacements:
        text = text.replace(a, b)
    return text.upper()

# ============================================================================================
# LÓGICA DE CANALES (Fusión y Filtrado)
# ============================================================================================

def load_csv_as_dict(filepath, key_field):
    data = {}
    if not filepath.exists():
        print(f"⚠️ Aviso: No se encuentra {filepath}")
        return data
    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if key_field in row and row[key_field]:
                data[row[key_field]] = row
    return data

def parse_m3u(content, source_tag):
    lines = content.splitlines()
    channels = []
    current_channel = {}
    
    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF:"):
            tvg_id_match = re.search(r'tvg-id="([^"]*)"', line)
            group_match = re.search(r'group-title="([^"]*)"', line)
            tvg_name_match = re.search(r'tvg-name="([^"]*)"', line)
            raw_name = line.split(',')[-1].strip()
            
            current_channel = {
                "tvg_id": tvg_id_match.group(1) if tvg_id_match else "",
                "group": group_match.group(1) if group_match else "OTROS",
                "tvg_name": tvg_name_match.group(1) if tvg_name_match else raw_name,
                "raw_name": raw_name,
                "clean_name": clean_name(raw_name),
                "source": source_tag
            }
        elif line.startswith("http") or line.startswith("acestream://"):
            current_channel["url"] = line
            if "getstream?id=" in line:
                current_channel["ace_id"] = line.split("id=")[-1]
            elif line.startswith("acestream://"):
                current_channel["ace_id"] = line.replace("acestream://", "")
            else:
                current_channel["ace_id"] = "unknown"
            
            channels.append(current_channel)
            current_channel = {}
            
    return channels

def process_channels():
    print("📥 Descargando listas M3U...")
    scraper = cloudscraper.create_scraper()
    
    try:
        req_elcano = scraper.get(URL_ELCANO)
        req_elcano.encoding = 'utf-8'
        channels_elcano = parse_m3u(req_elcano.text, "ELCANO")
        
        req_newera = scraper.get(URL_NEW_ERA)
        req_newera.encoding = 'utf-8'
        channels_newera = parse_m3u(req_newera.text, "NEW_ERA")
        
        # Guardar inputs crudos para referencia
        with open(FILE_ELCANO_OUT, 'w', encoding='utf-8') as f: f.write(req_elcano.text)
        with open(FILE_NEW_ERA_OUT, 'w', encoding='utf-8') as f: f.write(req_newera.text)
        
    except Exception as e:
        print(f"❌ Error descargando listas: {e}")
        if TEST_MODE: sys.exit(1)
        return

    # Cargar CSVs
    blacklist_data = load_csv_as_dict(FILE_LISTA_NEGRA, 'ace_id')
    
    all_channels = channels_elcano + channels_newera
    processed_channels = []
    
    print("⚙️ Procesando reglas de negocio y blacklist...")
    for ch in all_channels:
        ace_id = ch['ace_id']
        final_name = ch['clean_name']
        final_group = ch['group']
        is_blacklisted = "no"
        real_channel_name = ""

        # Lógica Lista Negra
        if ace_id in blacklist_data:
            is_blacklisted = "sí"
            bl_entry = blacklist_data[ace_id]
            real_channel_name = bl_entry.get('canal_real', '')
            final_group = "ZZ_Canales_KO"
            suffix_bl = f" >>> {real_channel_name}" if real_channel_name else " >>> BLACKLIST"
            final_name = f"{final_name}{suffix_bl}"

        processed_channels.append({
            "acestream_id": ace_id,
            "nombre_e": ch['raw_name'] if ch['source'] == "ELCANO" else "",
            "nombre_ne": ch['raw_name'] if ch['source'] == "NEW_ERA" else "",
            "tvg-id_e": ch['tvg_id'] if ch['source'] == "ELCANO" else "",
            "tvg-id_ne": ch['tvg_id'] if ch['source'] == "NEW_ERA" else "",
            "nombre_supuesto": final_name,
            "grupo_e": ch['group'] if ch['source'] == "ELCANO" else "",
            "grupo_ne": final_group,
            "calidad": "HD", 
            "lista_negra": is_blacklisted,
            "canal_real": real_channel_name,
            "url": ch['url']
        })

    # Ordenación: Grupo -> Nombre
    processed_channels.sort(key=lambda x: (x['grupo_ne'], x['nombre_supuesto']))
    
    # Escribir Outputs
    print(f"💾 Generando {FILE_EZDAKIT} y CSVs...")
    
    # CSV Correspondencias
    headers = ["acestream_id", "nombre_e", "nombre_ne", "tvg-id_e", "tvg-id_ne", 
               "nombre_supuesto", "grupo_e", "grupo_ne", "calidad", "lista_negra", "canal_real"]
    with open(FILE_CORRESPONDENCIAS, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for c in processed_channels:
            writer.writerow({k: c.get(k, '') for k in headers})

    # M3U Ezdakit
    with open(FILE_EZDAKIT, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/master/guiatv.xml" refresh="3600"\n')
        f.write('#EXTVLCOPT:network-caching=1000\n\n')
        for c in processed_channels:
            entry = f'#EXTINF:-1 group-title="{c["grupo_ne"]}" tvg-id="{c["tvg-id_ne"] or c["tvg-id_e"]}" tvg-name="{c["nombre_supuesto"]}",{c["nombre_supuesto"]}\n'
            entry += f'{c["url"]}\n'
            f.write(entry)

# ============================================================================================
# SCRAPING DE EVENTOS
# ============================================================================================

def scrape_events():
    print("⚽ Iniciando Scraping de Eventos...")
    
    # 1. Cargar Mapeo de Canales Oficiales
    official_channels = {}
    if FILE_LISTADO_CANALES.exists():
        with open(FILE_LISTADO_CANALES, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                clean_key = normalize_text(row['Canal'])
                if clean_key:
                    official_channels[clean_key] = row['Canal']
    
    # 2. Obtener HTML
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(URL_AGENDA)
        response.encoding = 'utf-8'
        html_content = response.text
        
        if TEST_MODE:
            debug_html = BASE_DIR / f"debug_html_downloaded{SUFFIX}.html"
            with open(debug_html, "w", encoding="utf-8") as f:
                f.write(html_content)
    except Exception as e:
        print(f"❌ Error scraping: {e}")
        return

    soup = BeautifulSoup(html_content, 'html.parser')
    lines = soup.get_text(separator="\n").splitlines()
    
    m3u_entries = []
    current_date = "HOY"
    
    regex_ace = re.compile(r'\b[a-f0-9]{40}\b')
    regex_time = re.compile(r'\b([0-2][0-9]:[0-5][0-9])\b')

    count = 0
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Detectar cabeceras de fecha
        if any(x in line.lower() for x in ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo', 'hoy', 'mañana']):
            if len(line) < 50 and not regex_ace.search(line):
                current_date = line
                continue

        # Detectar evento
        ace_match = regex_ace.search(line)
        if ace_match:
            ace_id = ace_match.group(0)
            time_match = regex_time.search(line)
            event_time = time_match.group(1) if time_match else "00:00"
            
            # Limpieza para extraer nombre
            clean_line = line.replace(ace_id, "").replace(event_time, "")
            
            # Detección inteligente de canal oficial
            norm_line = normalize_text(clean_line)
            detected_channel = "Unknown"
            longest_match = 0
            
            for key_norm, real_name in official_channels.items():
                if key_norm in norm_line and len(key_norm) > longest_match:
                    detected_channel = real_name
                    longest_match = len(key_norm)
            
            # Fallback: buscar paréntesis
            if detected_channel == "Unknown":
                par_match = re.search(r'\((.*?)\)', clean_line)
                if par_match:
                    detected_channel = par_match.group(1)
            
            # Limpiar nombre del evento
            event_name = clean_line
            if detected_channel != "Unknown" and detected_channel in event_name:
                event_name = event_name.replace(detected_channel, "")
            
            event_name = clean_name(event_name)
            prefix = ace_id[-3:]
            
            # Generar entrada
            display_name = f"{event_time}-{event_name} ({detected_channel}) (HD) ({prefix})"
            m3u_entry = f'#EXTINF:-1 group-title="{current_date}" tvg-name="{display_name}",{display_name}\nhttp://127.0.0.1:6878/ace/getstream?id={ace_id}'
            m3u_entries.append(m3u_entry)
            count += 1

    if m3u_entries:
        print(f"💾 Generando {FILE_EZDAKIT_EVENTOS} con {count} eventos...")
        with open(FILE_EZDAKIT_EVENTOS, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            f.write('\n'.join(m3u_entries))
    else:
        print("⚠️ No se encontraron eventos.")

# ============================================================================================
# MAIN
# ============================================================================================

if __name__ == "__main__":
    start_time = time.time()
    
    # Asegurar existencia carpeta salida
    if not DIR_CANALES.exists():
        DIR_CANALES.mkdir(parents=True)

    # 1. Procesar Lista Maestra
    process_channels()
    
    # 2. Procesar Eventos
    scrape_events()
    
    elapsed = time.time() - start_time
    print(f"\n✅ Proceso completado en {elapsed:.2f} segundos.")
