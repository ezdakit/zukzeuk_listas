import sqlite3
import requests
from datetime import datetime
import re
import sys

# Descargar el fichero M3U
url = "https://proxy.zeronet.dev/1H3KoazXt2gCJgeD8673eFvQYXG7cbRddU/lista-ott.m3u"
response = requests.get(url)
m3u_content = response.text

# Guardar una copia del fichero M3U descargado
with open('lista-ott.m3u', 'w') as file:
    file.write(m3u_content)

# Redirigir la salida de los print a un fichero de texto
sys.stdout = open('debug_log.txt', 'w')

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
print(f"Número total de líneas en el archivo M3U: {len(lines)}")

# Encontrar el índice de la primera línea que empieza por #EXTINF:-1
start_index = next((i for i, line in enumerate(lines) if line.startswith("#EXTINF:-1")), None)

if start_index is not None:
    for i in range(start_index, len(lines), 2):
        print(f"Procesando línea {i}: {lines[i]}")
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
            
            # Mensajes de depuración
            print(f"Procesando canal: {channel_name}")
            print(f"tvg-id: {tvg_id}")
            print(f"group-title: {group_title}")
            print(f"url: {url}")
            
            # Insertar en la base de datos
            cursor.execute('''
            INSERT INTO canales_iptv_temp (import_date, name_original, iptv_epg_id_original, iptv_epg_id_new, iptv_group_original, iptv_group_new, iptv_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (import_date, channel_name, tvg_id, "", group_title, "", url))

# Confirmar los cambios y cerrar la conexión
conn.commit()
conn.close()

print("Los datos se han insertado correctamente en zz_canales.db y se ha guardado una copia del fichero lista-ott.m3u")

# Cerrar el archivo de depuración
sys.stdout.close()
