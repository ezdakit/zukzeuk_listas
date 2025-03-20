import cloudscraper
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
import time
import csv
from bs4 import BeautifulSoup
import sys
import os
import re
import requests
from urllib3.exceptions import ReadTimeoutError
from datetime import datetime, timedelta

# Función para comparar dos archivos
def archivos_son_identicos(archivo1, archivo2):
    try:
        with open(archivo1, 'r') as f1, open(archivo2, 'r') as f2:
            return f1.read() == f2.read()
    except FileNotFoundError as e:
        logging.error(f"Error al abrir los archivos: {e}")
        sys.exit(1)  # Termina el script si no se pueden abrir los archivos

# Configuración de logging
logging.basicConfig(filename='debug_eventos.txt', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Borrar el contenido del fichero de log al inicio
with open('debug_eventos.txt', 'w'):
    pass

# URL de la página principal
url = 'http://127.0.0.1:43110/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie'

try:
    # Realizar la solicitud HTTP a la página web utilizando cloudscraper
    scraper = cloudscraper.create_scraper()
    response = scraper.get(url)
    response.raise_for_status()  # Verificar que la solicitud fue exitosa
    logging.info("Solicitud HTTP exitosa.")
except cloudscraper.exceptions.CloudflareChallengeError as e:
    logging.error(f"Error en la solicitud HTTP: {e}")
    raise
except requests.exceptions.RequestException as e:
    logging.error(f"La URL no está disponible o hubo un error en la solicitud: {e}")
    sys.exit(1)  # Termina el script con un código de error
except ReadTimeoutError as e:
    logging.error(f"Tiempo de espera agotado: {e}")
    sys.exit(1)  # Termina el script con un código de error

try:
    # Configurar Selenium para cargar el contenido dinámico
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Ejecutar Chrome en modo headless
    options.add_argument("--user-data-dir=/tmp/selenium_chrome_user_data_unique")

    driver = webdriver.Chrome(options=options)
    driver.get(url)

    # Aumentar el tiempo de espera a 30 segundos
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
    logging.info("Contenido de la página cargado correctamente.")

    # Obtener el contenido de la página principal
    html_main = driver.page_source

    # Guardar el contenido de la página principal en un archivo code.txt
    with open('code.txt', 'w', encoding='utf-8') as file:
        file.write(html_main)
    logging.info("El contenido de la página principal se ha guardado en 'code.txt'.")

    # Esperar a que el iframe esté presente
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'iframe')))

    # Cambiar al contenido del iframe
    driver.switch_to.frame(driver.find_element(By.TAG_NAME, 'iframe'))

    # Agregar un delay para esperar un poco antes de verificar la visibilidad de la tabla
    time.sleep(10)

    # Obtener el contenido del iframe
    iframe_html = driver.page_source
    driver.quit()
except Exception as e:
    logging.error(f"Error al cargar la página con Selenium: {e}")
    raise

try:
    # Guardar el contenido del iframe en un archivo code_iframe.txt
    if os.path.exists("code_iframe.txt"):    # Renombrar el archivo code_iframe.txt existente a code_iframe_old.txt
        os.rename("code_iframe.txt", "code_iframe_old.txt")
    with open('code_iframe.txt', 'w', encoding='utf-8') as file:
        file.write(iframe_html)
    logging.info("El contenido del iframe se ha guardado en 'code_iframe.txt'.")
except Exception as e:
    logging.error(f"Error al guardar el contenido del iframe en el archivo: {e}")
    raise

# Comparar los archivos antes de continuar
if archivos_son_identicos('code_iframe.txt', 'code_iframe_old.txt'):
    logging.info("Los archivos code_iframe.txt, code_iframe_old.txt son idénticos. Terminando el script.")
    sys.exit(0)  # Termina el script con éxito (código 0)

# Procesar el fichero code_iframe.txt para extraer información y generar el fichero eventos.csv
try:
    with open('code_iframe.txt', 'r', encoding='utf-8') as file:
        iframe_html = file.read()

    soup = BeautifulSoup(iframe_html, 'html.parser')
    table = soup.find('table', {'id': 'tablaEventos'})

    if table is None:
        logging.error("No se encontró la tabla con ID 'tablaEventos' en el iframe.")
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
    with open('eventos.csv', 'w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Hora', 'Competicion', 'Evento', 'Canales', 'Eventos_Acestream', 'Deporte'])
        writer.writerows(eventos)

    logging.info("El fichero eventos.csv se ha generado correctamente.")
except Exception as e:
    logging.error(f"Error al procesar el fichero code_iframe.txt: {e}")
    raise

# Procesar el fichero eventos.csv para generar zz_eventos_ott.m3u y zz_eventos_all_ott.m3u
try:
    # Ruta del archivo eventos.csv
    input_csv = 'eventos.csv'
    # Rutas de los archivos de salida
    output_m3u = 'zz_eventos_ott.m3u'
    output_all_m3u = 'zz_eventos_all_ott.m3u'

    # Cabecera del archivo M3U
    m3u_header = """#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml"
#EXTVLCOPT:network-caching=2000

"""

    # Obtener la fecha actual en UTC y convertirla a UTC+1
    now_utc = datetime.utcnow()  # Fecha y hora actual en UTC
    now_utc_plus_1 = now_utc + timedelta(hours=1)  # Sumar 1 hora para UTC+1
    fecha_formateada = now_utc_plus_1.strftime("%d de %B")  # Formato "día de mes"
    fecha_formateada_2 = now_utc_plus_1.strftime("%d-%m")  # Formato "día-mes"
    
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
                extinf_all_line = f'#EXTINF:-1 tvg-id="" group-title="{deporte}-{fecha_formateada_2.lower()}-{competicion}", {hora} {evento}\n'

                # Crear la línea de la URL
                url_line = f'http://127.0.0.1:6878/ace/getstream?id={eventos_acestream}\n'

                # Escribir ambas líneas en los archivos M3U
                m3u_file.write(extinf_line)
                m3u_file.write(url_line)

                m3u_all_file.write(extinf_all_line)
                m3u_all_file.write(url_line)

    logging.info("Los archivos zz_eventos_ott.m3u y zz_eventos_all_ott.m3u se han generado correctamente.")
except Exception as e:
    logging.error(f"Error al procesar el archivo CSV o generar los archivos M3U: {e}")
    raise

print("Proceso completado. Se han generado los archivos eventos.csv, zz_eventos_ott.m3u y zz_eventos_all_ott.m3u.")
