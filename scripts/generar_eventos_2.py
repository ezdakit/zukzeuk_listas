import logging
import time
import csv
from bs4 import BeautifulSoup
import sys
import os
import re
from datetime import datetime, timedelta
import locale
import shutil
import pytz

# Crear el directorio zz_eventos_2 si no existe
if not os.path.exists('zz_eventos_2'):
    os.makedirs('zz_eventos_2')

# Borrar el contenido del fichero de log al inicio
with open('zz_eventos_2/debug_eventos_2.txt', 'w'):
    pass

# Configuración de logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
file_handler = logging.FileHandler('zz_eventos_2/debug_eventos_2.txt')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')

# Verificar si el archivo existe
if not os.path.exists('eventos_2.html'):
    logger.error("El archivo eventos_2.html no existe. Verifica la ruta.")
    sys.exit(1)

# Procesar el fichero eventos_2.html para extraer información y generar el fichero eventos_2.csv
try:
    mod_time = os.path.getmtime('eventos_2.html')
    fecha_extraccion = datetime.fromtimestamp(mod_time)
    
    with open('eventos_2.html', 'r', encoding='utf-8') as file:
        html_content = file.read()

    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table', {'id': 'events-table'})

    if table is None:
        logger.error("No se encontró la tabla con ID 'events-table' en el archivo.")
        sys.exit(1)

    rows = table.find_all('tr')[1:]  # Saltar la fila de encabezados
    eventos = []

    for row in rows:
        cols = row.find_all('td')
        
        if len(cols) < 5:
            continue

        # Extraer datos de cada columna
        evento_completo = cols[0].text.strip()
        deporte = cols[1].text.strip()
        hora = cols[2].text.strip()
        estado = cols[3].text.strip()
        enlace = cols[4].find('a')['href'] if cols[4].find('a') else ''

        # Separar competición y evento del título
        if ": " in evento_completo:
            competicion, evento = evento_completo.split(": ", 1)
        else:
            competicion = evento_completo
            evento = evento_completo

        # Limpiar campos
        evento = " ".join(evento.split())
        evento = evento.replace(",", ".")
        competicion = " ".join(competicion.split())
        competicion = competicion.replace(",", ".")
        deporte = " ".join(deporte.split())
        deporte = deporte.replace(",", ".")

        eventos.append([hora, competicion, evento, estado, enlace, deporte])

    # Guardar los eventos en un archivo CSV
    with open('zz_eventos_2/eventos_2.csv', 'w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Hora', 'Competicion', 'Evento', 'Estado', 'Enlace', 'Deporte'])
        writer.writerows(eventos)

    logger.info("El fichero eventos_2.csv se ha generado correctamente.")
except Exception as e:
    logger.error(f"Error al procesar el fichero eventos_2.html: {e}")
    raise

# Verificar si el fichero eventos_2.csv tiene contenido antes de generar los archivos M3U
try:
    with open('zz_eventos_2/eventos_2.csv', 'r', encoding='utf-8') as file:
        reader = csv.reader(file)
        header = next(reader)
        if not any(reader):
            logger.info("El fichero eventos_2.csv no tiene eventos. Terminando el script.")
            sys.exit(0)
except Exception as e:
    logger.error(f"Error al verificar el contenido del fichero eventos_2.csv: {e}")
    raise

# Procesar el fichero eventos_2.csv para generar zz_eventos_2_ott.m3u y zz_eventos_2_all_ott.m3u
try:
    input_csv = 'zz_eventos_2/eventos_2.csv'
    output_m3u = 'zz_eventos_2/zz_eventos_2_ott.m3u'
    output_all_m3u = 'zz_eventos_2/zz_eventos_2_all_ott.m3u'

    m3u_header = """#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml"
#EXTVLCOPT:network-caching=2000

"""

    fecha_extraccion_utc = fecha_extraccion.replace(tzinfo=pytz.utc)
    madrid_tz = pytz.timezone('Europe/Madrid')
    fecha_madrid = fecha_extraccion_utc.astimezone(madrid_tz)
    
    fecha_formateada = fecha_madrid.strftime("%d de %B").lower()
    fecha_formateada_2 = fecha_madrid.strftime("[%d/%m]").lower()
    
    with open(input_csv, 'r', encoding='utf-8') as csv_file:
        csv_reader = csv.reader(csv_file)
        next(csv_reader)

        with open(output_m3u, 'w', encoding='utf-8') as m3u_file, \
             open(output_all_m3u, 'w', encoding='utf-8') as m3u_all_file:

            m3u_file.write(m3u_header)
            m3u_all_file.write(m3u_header)

            for row in csv_reader:
                hora, competicion, evento, estado, enlace, deporte = row

                extinf_line = f'#EXTINF:-1 tvg-id="" group-title="# Eventos {fecha_formateada} por horario", {hora} {evento}\n'
                extinf_all_line = f'#EXTINF:-1 tvg-id="" group-title="{deporte} {fecha_formateada_2} {competicion}", {hora} {evento}\n'
                url_line = f'{enlace}\n'  # Usamos la URL directamente tal cual

                m3u_file.write(extinf_line)
                m3u_file.write(url_line)

                m3u_all_file.write(extinf_all_line)
                m3u_all_file.write(url_line)

    logger.info("Los archivos zz_eventos_2_ott.m3u y zz_eventos_2_all_ott.m3u se han generado correctamente.")
except Exception as e:
    logger.error(f"Error al procesar el archivo CSV o generar los archivos M3U: {e}")
    raise

# Copiar los archivos M3U al directorio raíz del repositorio
try:
    m3u_files = ['zz_eventos_2/zz_eventos_2_ott.m3u', 'zz_eventos_2/zz_eventos_2_all_ott.m3u']

    for m3u_file in m3u_files:
        shutil.copy(m3u_file, './')

    logger.info("Los archivos M3U se han copiado al directorio raíz del repositorio.")
except Exception as e:
    logger.error(f"Error al copiar los archivos M3U al directorio raíz: {e}")
    raise

print("Proceso completado. Se han generado los archivos eventos_2.csv, zz_eventos_2_ott.m3u y zz_eventos_2_all_ott.m3u.")
