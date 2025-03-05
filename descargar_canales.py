import sqlite3
import requests
from datetime import datetime
import re
import sys

# Descargar el fichero M3U
url = "https://proxy.zeronet.dev/1H3KoazXt2gCJgeD8673eFvQYXG7cbRddU/lista-ott.m3u"
try:
    response = requests.get(url)
    response.raise_for_status()
    m3u_content = response.content.decode('utf-8', errors='replace')  # Decodificar el contenido como UTF-8
except requests.RequestException as e:
    print(f"Error al descargar el archivo M3U: {e}")
    sys.exit(1)

# Guardar una copia del fichero M3U descargado
with open('lista-ott.m3u', 'w', encoding='utf-8') as file:
    file.write(m3u_content)

# Redirigir la salida de los print a fichero de texto
sys.stdout = open('debug_log.txt', 'w', encoding='utf-8')

# Conectar a la base de datos SQLite
try:
    conn = sqlite3.connect('zz_canales.db')
    cursor = conn.cursor()

    # Configurar la conexión para usar UTF-8
    cursor.execute('PRAGMA encoding = "UTF-8";')

    # Crear la tabla si no existe, incluyendo el nuevo campo "activo"
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS canales_iptv_temp (
        import_date TEXT,
        name_original TEXT,
        iptv_epg_id_original TEXT,
        iptv_epg_id_new TEXT,
        iptv_group_original TEXT,
        iptv_group_new TEXT,
        iptv_url TEXT,
        name_new TEXT,
        activo INTEGER DEFAULT 0
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
                channel_name = extinf_parts[-1].strip()  # Eliminar espacios al principio y al final
                
                # Usar expresiones regulares para extraer tvg-id y group-title
                tvg_id_match = re.search(r'tvg-id="([^"]+)"', lines[i])
                group_title_match = re.search(r'group-title="([^"]+)"', lines[i])
                tvg_id = tvg_id_match.group(1) if tvg_id_match else ""
                group_title = group_title_match.group(1) if group_title_match else ""
                
                # Obtener la URL de la siguiente línea
                url = lines[i + 1] if i + 1 < len(lines) else ""
                
                # Limpiar caracteres no deseados
                channel_name = re.sub(r'[^\x00-\x7F]+', '', channel_name)
                tvg_id = re.sub(r'[^\x00-\x7F]+', '', tvg_id)
                group_title = re.sub(r'[^\x00-\x7F]+', '', group_title)
                url = re.sub(r'[^\x00-\x7F]+', '', url)
                
                # Mensajes de depuración
                print(f"Procesando canal: {channel_name}")
                print(f"tvg-id: {tvg_id}")
                print(f"group-title: {group_title}")
                print(f"url: {url}")
                
                # Insertar en la base de datos, estableciendo "activo" a 0 por defecto
                cursor.execute('''
                INSERT INTO canales_iptv_temp (import_date, name_original, iptv_epg_id_original, iptv_epg_id_new, iptv_group_original, iptv_group_new, iptv_url, name_new, activo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (import_date, channel_name, tvg_id, "", group_title, "", url, "", 0))

    # Actualizar los registros de canales_iptv_temp con los datos de correspondencia_canales
    cursor.execute('''
    UPDATE canales_iptv_temp
    SET iptv_epg_id_new = (
        SELECT channel_epg_id FROM correspondencia_canales
        WHERE correspondencia_canales.channel_iptv_name = canales_iptv_temp.name_original
    ),
    iptv_group_new = (
        SELECT channel_group FROM correspondencia_canales
        WHERE correspondencia_canales.channel_iptv_name = canales_iptv_temp.name_original
    ),
    name_new = (
        SELECT channel_name FROM correspondencia_canales
        WHERE correspondencia_canales.channel_iptv_name = canales_iptv_temp.name_original
    ),
    activo = 1
    WHERE EXISTS (
        SELECT 1 FROM correspondencia_canales
        WHERE correspondencia_canales.channel_iptv_name = canales_iptv_temp.name_original
    )
    ''')

    # Confirmar los cambios
    conn.commit()

    # Generar el archivo zz_lista_ott.m3u
    with open('zz_lista_ott.m3u', 'w', encoding='utf-8') as m3u_file:
        m3u_file.write('#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml"\n')
        m3u_file.write('#EXTVLCOPT:network-caching=2000\n\n')
        
        for row in cursor.execute('SELECT iptv_epg_id_new, iptv_group_new, name_new, iptv_url FROM canales_iptv_temp WHERE activo = 1'):
            iptv_epg_id_new, iptv_group_new, name_new, iptv_url = row
            m3u_file.write(f'#EXTINF:-1 tvg-id="{iptv_epg_id_new}" group-title="{iptv_group_new}", {name_new}\n')
            m3u_file.write(f'{iptv_url}\n')

except sqlite3.Error as e:
    print(f"Error al trabajar con la base de datos: {e}")
finally:
    # Cerrar la conexión a la base de datos
    if conn:
        conn.close()

# Cerrar el archivo de depuración
sys.stdout.close()

# Redirigir la salida de vuelta a la consola estándar
sys.stdout = sys.__stdout__

# Imprimir el mensaje final
print("Los datos se han insertado correctamente en zz_canales.db y se ha generado el fichero zz_lista_ott.m3u")