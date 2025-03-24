import logging
import time
import csv
from bs4 import BeautifulSoup
import sys
import os
import re
from datetime import datetime, timedelta
import locale
import shutil  # Importar shutil para operaciones de archivos

# Borrar el contenido del fichero de log al inicio
with open('zz_eventos/debug_eventos.txt', 'w'):
    pass

# Configuración de logging con fecha y hora en cada línea
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
file_handler = logging.FileHandler('zz_eventos/debug_eventos.txt')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')) # Asegurar que el formato se aplica al manejador de archivo
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')) # Asegurar que el formato se aplica al manejador de consola
logger.addHandler(file_handler)
logger.addHandler(console_handler)

locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')  # Configura el idioma a español


# Procesar el fichero eventos.html para extraer información y generar el fichero eventos.csv
try:
    with open('zn_downloads/eventos.html', 'r', encoding='utf-8') as file:
        primera_linea = file.readline()  # Leer la primera línea del archivo
        iframe_html = primera_linea + file.read()  # Concatenar la primera línea con el resto del contenido

    # Extraer la fecha y hora de extracción de la primera línea
    fecha_extraccion_match = re.search(r'<!-- Fecha y hora de extracción: (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z) -->', primera_linea)
    if not fecha_extraccion_match:
        logger.error("No se encontró la fecha y hora de extracción en el fichero eventos.html.")
        sys.exit(1)  # Terminar el script con un código de error

    fecha_extraccion_str = fecha_extraccion_match.group(1)
    fecha_extraccion = datetime.strptime(fecha_extraccion_str, "%Y-%m-%dT%H:%M:%S.%fZ")

    soup = BeautifulSoup(iframe_html, 'html.parser')
    table = soup.find('table', {'id': 'tablaEventos'})

    if table is None:
        logger.error("No se encontró la tabla con ID 'tablaEventos' en el iframe.")
        sys.exit(1)  # Terminar el script con un código de error

    rows = table.find_all('tr')
    eventos = []

    for row in rows[1:]:  # Saltar la primera fila que contiene los encabezados
        cols = row.find_all('td')
        
        # Verificar que hay suficientes columnas
        if len(cols) < 5:
            continue  # Saltar filas con formato incorrecto

        # Extraer datos de cada columna INDIVIDUAL
        hora = cols[0].text.strip()          # Primera columna (índice 0)
        competicion = cols[1].text.strip()   # Segunda columna (índice 1)
        evento = cols[2].text.strip()        # Tercera columna (índice 2)
        # La columna de "Canales" (índice 3) está oculta, no la necesitamos
        eventos_acestream = cols[4].find_all('a')  # Buscar en la columna de "Eventos Acestream" (índice 4)

        # Limpiar el campo "Evento" (eliminar comas, saltos de línea y espacios adicionales)
        evento = " ".join(evento.split())  # Elimina espacios múltiples y saltos de línea
        evento = evento.replace(",", ".")  # Sustituye comas por puntos

        # Extraer el deporte del campo "Competición"
        # Buscar la URL de la imagen en el campo "Competición"
        match = re.search(r'src="https://static\.futbolenlatv\.com/img/32/\d+-(.*?)\.webp"', str(cols[1]))
        if match:
            # Extraer el texto entre el último punto y el primer guion
            deporte = match.group(1).split('-')[-1]

        # Procesar cada enlace de Acestream
        for evento_acestream in eventos_acestream:
            nombre_canal = evento_acestream.text.strip()
            url_acestream = evento_acestream['href'].replace('acestream://', '')
            eventos.append([hora, competicion, evento, nombre_canal, url_acestream, deporte])

    # Guardar los eventos en un archivo CSV
    with open('zz_eventos/eventos.csv', 'w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Hora', 'Competicion', 'Evento', 'Canales', 'Eventos_Acestream', 'Deporte'])
        writer.writerows(eventos)

    logger.info("El fichero eventos.csv se ha generado correctamente.")
except Exception as e:
    logger.error(f"Error al procesar el fichero eventos.html: {e}")
    raise

# Verificar si el fichero eventos.csv tiene contenido antes de generar los archivos M3U
try:
    with open('zz_eventos/eventos.csv', 'r', encoding='utf-8') as file:
        reader = csv.reader(file)
        header = next(reader)  # Leer la cabecera
        if not any(reader):  # Verificar si hay alguna línea adicional
            logger.info("El fichero eventos.csv no tiene eventos. Terminando el script.")
            sys.exit(0)  # Terminar el script sin generar los archivos M3U
except Exception as e:
    logger.error(f"Error al verificar el contenido del fichero eventos.csv: {e}")
    raise

# Procesar el fichero eventos.csv para generar zz_eventos_ott.m3u y zz_eventos_all_ott.m3u
try:
    # Ruta del archivo eventos.csv
    input_csv = 'zz_eventos/eventos.csv'
    # Rutas de los archivos de salida
    output_m3u = 'zz_eventos/zz_eventos_ott.m3u'
    output_all_m3u = 'zz_eventos/zz_eventos_all_ott.m3u'

    # Cabecera del archivo M3U
    m3u_header = """#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml"
#EXTVLCOPT:network-caching=2000

"""

    # Obtener la fecha de extracción y convertirla a UTC+1
    fecha_extraccion_utc_plus_1 = fecha_extraccion + timedelta(hours=1)  # Sumar 1 hora para UTC+1
    fecha_formateada = fecha_extraccion_utc_plus_1.strftime("%d de %B")  # Formato "día de mes"
    fecha_formateada_2 = fecha_extraccion_utc_plus_1.strftime("[%d/%m]")  # Formato "día/mes"
    
    # Abrir el archivo CSV para lectura
    with open(input_csv, 'r', encoding='utf-8') as csv_file:
        csv_reader = csv.reader(csv_file)
        next(csv_reader)  # Saltar la primera fila (encabezados)

        # Abrir los archivos M3U para escritura
        with open(output_m3u, 'w', encoding='utf-8') as m3u_file, \
             open(output_all_m3u, 'w', encoding='utf-8') as m3u_all_file:

            # Escribir la cabecera en ambos archivos M3U
            m3u_file.write(m3u_header)
            m3u_all_file.write(m3u_header)

            # Procesar cada línea del CSV
            for row in csv_reader:
                hora, competicion, evento, nombre_canal, eventos_acestream, deporte = row

                # Crear la línea #EXTINF para zz_eventos_ott.m3u (group-title="# Eventos [fecha] por horario")
                extinf_line = f'#EXTINF:-1 tvg-id="" group-title="# Eventos {fecha_formateada.lower()} por horario", {hora} {evento}\n'

                # Crear la línea #EXTINF para zz_eventos_all_ott.m3u (group-title con el contenido de "Competicion")
                extinf_all_line = f'#EXTINF:-1 tvg-id="" group-title="{deporte} {fecha_formateada_2.lower()} {competicion}", {hora} {evento}\n'

                # Crear la línea de la URL
                url_line = f'http://127.0.0.1:6878/ace/getstream?id={eventos_acestream}\n'

                # Escribir ambas líneas en los archivos M3U
                m3u_file.write(extinf_line)
                m3u_file.write(url_line)

                m3u_all_file.write(extinf_all_line)
                m3u_all_file.write(url_line)

    logger.info("Los archivos zz_eventos_ott.m3u y zz_eventos_all_ott.m3u se han generado correctamente.")
except Exception as e:
    logger.error(f"Error al procesar el archivo CSV o generar los archivos M3U: {e}")
    raise

# Copiar los archivos M3U al directorio raíz del repositorio
try:
    # Ruta de los archivos M3U en la carpeta zz_eventos
    m3u_files = ['zz_eventos/zz_eventos_ott.m3u', 'zz_eventos/zz_eventos_all_ott.m3u']

    # Copiar cada archivo al directorio raíz
    for m3u_file in m3u_files:
        shutil.copy(m3u_file, './')

    logger.info("Los archivos M3U se han copiado al directorio raíz del repositorio.")
except Exception as e:
    logger.error(f"Error al copiar los archivos M3U al directorio raíz: {e}")
    raise

print("Proceso completado. Se han generado los archivos eventos.csv, zz_eventos_ott.m3u y zz_eventos_all_ott.m3u.")
