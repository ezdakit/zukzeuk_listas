import sqlite3
import requests
from datetime import datetime

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

# Obtener la fecha y hora actual para el campo import_date
import_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

# Procesar el contenido del fichero M3U e insertar en la base de datos
lines = m3u_content.splitlines()
for i in range(3, len(lines), 2):
    if lines[i].startswith("#EXTINF:-1"):
        # Extraer tvg-id, group-title y nombre del canal
        extinf_parts = lines[i].split(',')
        channel_name = extinf_parts[-1]
        tags = extinf_parts[0].split(' ')
        tvg_id = ""
        group_title = ""
        for tag in tags:
            if tag.startswith('tvg-id='):
                tvg_id = tag.split('=')[1].strip('"')
            elif tag.startswith('group-title='):
                group_title = tag.split('=')[1].strip('"')
        
        # Obtener la URL de la siguiente línea
        url = lines[i + 1]
        
        # Insertar en la base de datos
        cursor.execute('''
        INSERT INTO canales_iptv_temp (import_date, name_original, iptv_epg_id_original, iptv_epg_id_new, iptv_group_original, iptv_group_new, iptv_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (import_date, channel_name, tvg_id, "", group_title, "", url))

# Confirmar los cambios y cerrar la conexión
conn.commit()
conn.close()

print("Los datos se han insertado correctamente en zz_canales.db")
