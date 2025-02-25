import sqlite3
import requests
from datetime import datetime
import re

# Descargar el fichero M3U
url = "https://proxy.zeronet.dev/1H3KoazXt2gCJgeD8673eFvQYXG7cbRddU/lista-ott.m3u"
response = requests.get(url)
m3u_content = response.text

# Conectar a la base de datos SQLite
conn = sqlite3.connect('zz_canales.db')
cursor = conn.cursor()

# Crear la tabla si no existe
cursor.execute('''
CREATE TABLE IF NOT EXISTS canales_iptv_temp (
    import_date TEXT,
    name_original TEXT,
    iptv_epg_id_original TEXT,
    iptv_epg_id_new TEXT,
    iptv_group_original TEXT,
    iptv_group_new TEXT,
    iptv_url TEXT
)
''')

# Borrar todos los registros de la tabla si existe
cursor.execute('DELETE FROM canales_iptv_temp')

# Obtener la fecha y hora actual para el campo import_date
import_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

# Procesar el contenido del fichero M3U e insertar en la base de datos
lines = m3u_content.splitlines()
for i in range(0, len(lines), 2):  # Comenzar desde el inicio
    if lines[i].startswith("#EXTINF:-1"):
        # Extraer tvg-id, group-title y nombre del canal usando expresiones regulares
        extinf_parts = lines[i].split(',')
        channel_name = extinf_parts[-1]
        
        # Usar expresiones regulares para extraer tvg-id y group-title
        tvg_id_match = re.search(r'tvg-id="([^"]+)"', lines[i])
        group_title_match = re.search(r'group-title="([^"]+)"', lines[i])
        tvg_id = tvg_id_match.group(1) if tvg_id_match else ""
        group_title = group_title_match.group(1) if group_title_match else ""
        
        # Obtener la URL de la siguiente línea
        url = lines[i + 1] if i + 1 < len(lines) else ""
        
        # Insertar en la base de datos
        cursor.execute('''
        INSERT INTO canales_iptv_temp (import_date, name_original, iptv_epg_id_original, iptv_epg_id_new, iptv_group_original, iptv_group_new, iptv_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (import_date, channel_name, tvg_id, "", group_title, "", url))

# Confirmar los cambios y cerrar la conexión
conn.commit()
conn.close()

print("Los datos se han insertado correctamente en zz_canales.db")
