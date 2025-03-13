import sqlite3
import requests
from datetime import datetime
import re
import sys
import logging
import Levenshtein
import os
import csv

# Configuración de logging
logging.basicConfig(filename='debug_log.txt', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Borrar el contenido del fichero de log al inicio
with open('debug_log.txt', 'w'):
    pass

# Borrar el fichero cambios.txt si existe al inicio
if os.path.exists('cambios.txt'):
    os.remove('cambios.txt')

# Descargar el fichero M3U
url = "https://proxy.zeronet.dev/1H3KoazXt2gCJgeD8673eFvQYXG7cbRddU/lista-ott.m3u"
try:
    response = requests.get(url)
    response.raise_for_status()
    m3u_content = response.content.decode('utf-8', errors='replace')
except requests.RequestException as e:
    logging.error(f"Error al descargar el archivo M3U: {e}")
    sys.exit(1)

# Guardar una copia del fichero M3U descargado
with open('lista-ott.m3u', 'w', encoding='utf-8') as file:
    file.write(m3u_content)

# Comparar con el archivo existente (si existe)
try:
    with open('lista-ott-prev.m3u', 'r', encoding='utf-8') as prev_file:
        prev_m3u_content = prev_file.read()
except FileNotFoundError:
    prev_m3u_content = ""

if m3u_content == prev_m3u_content:
    logging.info("No hay cambios en el archivo M3U. Deteniendo la ejecución del script.")
    sys.exit(0)
else:
    # Guardar el nuevo archivo como el archivo anterior para la próxima comparación
    with open('lista-ott-prev.m3u', 'w', encoding='utf-8') as prev_file:
        prev_file.write(m3u_content)

    # Encontrar las líneas nuevas que no estaban en el archivo anterior
    new_lines = [line for line in m3u_content.splitlines() if line.startswith("#EXTINF") and line not in prev_m3u_content.splitlines()]
    logging.info(f"Se encontraron {len(new_lines)} líneas nuevas en el archivo M3U.")
    # Incluir las líneas nuevas en cambios.txt
    with open('cambios.txt', 'w', encoding='utf-8') as cambios_file:
        for line in new_lines:
            logging.info(f"Línea nueva: {line}")
            cambios_file.write(f"{line}\n")

# Conectar a la base de datos SQLite
try:
    conn = sqlite3.connect('zz_canales.db')
    cursor = conn.cursor()
    cursor.execute('PRAGMA encoding = "UTF-8";')

    # Eliminar la tabla correspondencia_canales si existe
    cursor.execute('DROP TABLE IF EXISTS correspondencia_canales')
    
    # Crear la tabla correspondencia_canales de nuevo
    create_table_query = '''
    CREATE TABLE "correspondencia_canales" (
        "channel_root" TEXT UNIQUE,
        "channel_epg_id" TEXT,
        "channel_name" TEXT,
        "channel_group" TEXT,
        "id" INTEGER PRIMARY KEY AUTOINCREMENT
    )
    '''
    cursor.execute(create_table_query)
    
    # Abrir el fichero CSV e insertar registros en la tabla
    with open('correspondencia_canales.csv', mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file, delimiter=';')
        for row in reader:
            if 'channel_root' in row and 'channel_epg_id' in row and 'channel_name' in row and 'channel_group' in row:
                cursor.execute('''
                    INSERT INTO correspondencia_canales (channel_root, channel_epg_id, channel_name, channel_group)
                    VALUES (?, ?, ?, ?)
                ''', (row['channel_root'], row['channel_epg_id'], row['channel_name'], row['channel_group']))
            else:
                print("Falta una de las claves necesarias en la fila:", row)

    # Eliminar la tabla correspondencia_canales si existe
    cursor.execute('DROP TABLE IF EXISTS canales_iptv_temp')
    # volver a crearla
    cursor.execute('''CREATE TABLE IF NOT EXISTS canales_iptv_temp (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        import_date TEXT,
        name_original TEXT,
        name_new TEXT,
        iptv_epg_id_original TEXT,
        iptv_epg_id_new TEXT,
        iptv_group_original TEXT,
        iptv_group_new TEXT,
        FHD INTEGER,
        iptv_url TEXT,
        activo INTEGER DEFAULT 0
    )''')
    cursor.execute('DELETE FROM canales_iptv_temp')

    import_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    lines = m3u_content.splitlines()
    logging.info(f"Número total de líneas en el archivo M3U: {len(lines)}")

    start_index = next((i for i, line in enumerate(lines) if line.startswith("#EXTINF:-1")), None)
    if start_index is not None:
        for i in range(start_index, len(lines), 2):
            # logging.debug(f"Procesando línea {i}: {lines[i]}")
            if lines[i].startswith("#EXTINF:-1"):
                extinf_parts = lines[i].split(',')
                channel_name = extinf_parts[-1].strip().upper()
                tvg_id_match = re.search(r'tvg-id="([^"]+)"', lines[i])
                group_title_match = re.search(r'group-title="([^"]+)"', lines[i])
                tvg_id = tvg_id_match.group(1) if tvg_id_match else ""
                group_title = group_title_match.group(1) if group_title_match else ""
                url = lines[i + 1] if i + 1 < len(lines) else ""
                channel_name = re.sub(r'[^\x00-\x7F]+', '', channel_name)
                tvg_id = re.sub(r'[^\x00-\x7F]+', '', tvg_id)
                group_title = re.sub(r'[^\x00-\x7F]+', '', group_title)
                url = re.sub(r'[^\x00-\x7F]+', '', url)
                logging.info(f"Procesando canal: {channel_name}")
                # logging.debug(f"tvg-id: {tvg_id}")
                # logging.debug(f"group-title: {group_title}")
                # logging.debug(f"url: {url}")

                # Determinar si el canal es FHD
                if "FHD" in channel_name or "1080" in channel_name:
                    fhd = 1  # Es FHD
                else:
                    fhd = 0  # No es FHD
    
                # Insertar el registro en la tabla canales_iptv_temp
                cursor.execute('''INSERT INTO canales_iptv_temp (
                    import_date, name_original, iptv_epg_id_original, iptv_epg_id_new, iptv_group_original, iptv_group_new, iptv_url, name_new, activo, FHD
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (import_date, channel_name, tvg_id, "", group_title, "", url, "", 0, fhd))
                
    cursor.execute("SELECT id, name_original FROM canales_iptv_temp")
    canales_iptv_temp = cursor.fetchall()
    for canal in canales_iptv_temp:
        id_temp, name_original = canal
        cursor.execute("SELECT id, channel_root, channel_epg_id, channel_group, channel_name FROM correspondencia_canales WHERE ? LIKE '%' || channel_root || '%'", (name_original,))
        posibles_correspondencias = cursor.fetchall()
        if posibles_correspondencias:
            mejor_correspondencia = min(posibles_correspondencias, key=lambda x: Levenshtein.distance(name_original, x[1]))
            cursor.execute('''UPDATE canales_iptv_temp SET activo = 1, iptv_epg_id_new = ?, iptv_group_new = ?, name_new = ? WHERE id = ?''', (mejor_correspondencia[2], mejor_correspondencia[3], mejor_correspondencia[4], id_temp))
        else:
            cursor.execute("UPDATE canales_iptv_temp SET activo = 0 WHERE id = ?", (id_temp,))

    conn.commit()

    # Borrar el fichero canales_iptv_temp.csv si existe
    if os.path.exists('canales_iptv_temp.csv'):
        os.remove('canales_iptv_temp.csv')
    
    # Exportar la tabla canales_iptv_temp a un archivo CSV
    try:
        with open('canales_iptv_temp.csv', 'w', encoding='utf-8', newline='') as csv_file:
            csv_writer = csv.writer(csv_file, delimiter=';')
            
            # Escribir la cabecera del CSV
            cursor.execute("PRAGMA table_info(canales_iptv_temp)")
            columns = cursor.fetchall()
            header = [column[1] for column in columns]  # Obtener los nombres de las columnas
            csv_writer.writerow(header)
            
            # Escribir los datos de la tabla
            cursor.execute("SELECT * FROM canales_iptv_temp")
            rows = cursor.fetchall()
            for row in rows:
                csv_writer.writerow(row)
        logging.info("Se ha exportado la tabla canales_iptv_temp a canales_iptv_temp.csv")
    except Exception as e:
        logging.error(f"Error al exportar la tabla canales_iptv_temp a CSV: {e}")


    # Generar el archivo zz_lista_ott.m3u
    try:
        with open('zz_lista_ott.m3u', 'w', encoding='utf-8') as m3u_file:
            m3u_file.write('#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml"\n')
            m3u_file.write('#EXTVLCOPT:network-caching=2000\n\n')

            # Primero escribimos los registros con activo = 1
            for row in cursor.execute('SELECT iptv_epg_id_new, iptv_group_new, name_new, iptv_url, FHD FROM canales_iptv_temp WHERE activo = 1 ORDER BY iptv_group_new, name_new'):
                iptv_epg_id_new, iptv_group_new, name_new, iptv_url, fhd = row
                
                # Añadir " [FHD]" o " [HD]" al nombre del canal según el valor de FHD
                if fhd == 1:
                    name_new_with_quality = f"{name_new} - FHD"
                else:
                    name_new_with_quality = f"{name_new} - HD"
                
                m3u_file.write(f'#EXTINF:-1 tvg-id="{iptv_epg_id_new}" group-title="{iptv_group_new}", {name_new_with_quality}\n')
                m3u_file.write(f'{iptv_url}\n')
            
            # Luego escribimos los registros con activo = 0
            for row in cursor.execute('SELECT iptv_epg_id_original, name_original, iptv_url FROM canales_iptv_temp WHERE activo = 0 ORDER BY name_original'):
                iptv_epg_id_original, name_original, iptv_url = row
                # Eliminar " -->" y todo el texto que le sigue en name_original
                if " -->" in name_original:
                    name_original = name_original.split(" -->")[0].strip()
                m3u_file.write(f'#EXTINF:-1 tvg-id="{iptv_epg_id_original}" group-title="VARIOS", {name_original}\n')
                m3u_file.write(f'{iptv_url}\n')
    except Exception as e:
        logging.error(f"Error al generar zz_lista_ott.m3u: {e}")

    # Generar el archivo zz_lista_ace.m3u
    try:
        with open('zz_lista_ace.m3u', 'w', encoding='utf-8') as ace_file:
            ace_file.write('#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml"\n')
            ace_file.write('#EXTVLCOPT:network-caching=2000\n\n')

            # Primero escribimos los registros con activo = 1
            for row in cursor.execute('SELECT iptv_epg_id_new, iptv_group_new, name_new, iptv_url, FHD FROM canales_iptv_temp WHERE activo = 1 ORDER BY iptv_group_new, name_new'):
                iptv_epg_id_new, iptv_group_new, name_new, iptv_url, fhd = row
                
                # Añadir " [FHD]" o " [HD]" al nombre del canal según el valor de FHD
                if fhd == 1:
                    name_new_with_quality = f"{name_new} - FHD"
                else:
                    name_new_with_quality = f"{name_new} - HD"
                
                ace_file.write(f'#EXTINF:-1 tvg-id="{iptv_epg_id_new}" group-title="{iptv_group_new}", {name_new_with_quality}\n')
                ace_url = iptv_url.replace("http://127.0.0.1:6878/ace/getstream?id=", "acestream://")
                ace_file.write(f'{ace_url}\n')
            
            # Luego escribimos los registros con activo = 0
            for row in cursor.execute('SELECT iptv_epg_id_original, name_original, iptv_url FROM canales_iptv_temp WHERE activo = 0 ORDER BY name_original'):
                iptv_epg_id_original, name_original, iptv_url = row
                # Eliminar " -->" y todo el texto que le sigue en name_original
                if " -->" in name_original:
                    name_original = name_original.split(" -->")[0].strip()
                ace_file.write(f'#EXTINF:-1 tvg-id="{iptv_epg_id_original}" group-title="VARIOS", {name_original}\n')
                ace_url = iptv_url.replace("http://127.0.0.1:6878/ace/getstream?id=", "acestream://")
                ace_file.write(f'{ace_url}\n')
    except Exception as e:
        logging.error(f"Error al generar zz_lista_ace.m3u: {e}")
    
    # Generar el archivo zz_lista_kodi.m3u
    try:
        with open('zz_lista_kodi.m3u', 'w', encoding='utf-8') as kodi_file:
            kodi_file.write('#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml"\n')
            kodi_file.write('#EXTVLCOPT:network-caching=2000\n\n')

            # Primero escribimos los registros con activo = 1
            for row in cursor.execute('SELECT iptv_epg_id_new, iptv_group_new, name_new, iptv_url, FHD FROM canales_iptv_temp WHERE activo = 1 ORDER BY iptv_group_new, name_new'):
                iptv_epg_id_new, iptv_group_new, name_new, iptv_url, fhd = row
                
                # Añadir " [FHD]" o " [HD]" al nombre del canal según el valor de FHD
                if fhd == 1:
                    name_new_with_quality = f"{name_new} - FHD"
                else:
                    name_new_with_quality = f"{name_new} - HD"
                
                kodi_file.write(f'#EXTINF:-1 tvg-id="{iptv_epg_id_new}" group-title="{iptv_group_new}", {name_new_with_quality}\n')
                kodi_url = iptv_url.replace("http://127.0.0.1:6878/ace/getstream?id=", "plugin://script.module.horus?action=play&id=")
                kodi_file.write(f'{kodi_url}\n')
            
            # Luego escribimos los registros con activo = 0
            for row in cursor.execute('SELECT iptv_epg_id_original, name_original, iptv_url FROM canales_iptv_temp WHERE activo = 0 ORDER BY name_original'):
                iptv_epg_id_original, name_original, iptv_url = row
                # Eliminar " -->" y todo el texto que le sigue en name_original
                if " -->" in name_original:
                    name_original = name_original.split(" -->")[0].strip()
                kodi_file.write(f'#EXTINF:-1 tvg-id="{iptv_epg_id_original}" group-title="VARIOS", {name_original}\n')
                kodi_url = iptv_url.replace("http://127.0.0.1:6878/ace/getstream?id=", "plugin://script.module.horus?action=play&id=")
                kodi_file.write(f'{kodi_url}\n')
    except Exception as e:
        logging.error(f"Error al generar zz_lista_kodi.m3u: {e}")
    
finally:
    if conn:
        conn.close()

logging.info("Los datos se han insertado correctamente en zz_canales.db y se han generado los ficheros zz_lista_ott.m3u, zz_lista_ace.m3u y zz_lista_kodi.m3u")
