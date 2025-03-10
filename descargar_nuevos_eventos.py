import cloudscraper
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
import time
import csv
from bs4 import BeautifulSoup

# Configuración de logging
logging.basicConfig(filename='debug_eventos.txt', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# URL de la página principal
url = 'https://proxy.zeronet.dev/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie'

try:
    # Realizar la solicitud HTTP a la página web utilizando cloudscraper
    scraper = cloudscraper.create_scraper()
    response = scraper.get(url)
    response.raise_for_status()  # Verificar que la solicitud fue exitosa
    logging.info("Solicitud HTTP exitosa.")
except cloudscraper.exceptions.CloudflareChallengeError as e:
    logging.error(f"Error en la solicitud HTTP: {e}")
    raise

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
    time.sleep(5)

    # Obtener el contenido del iframe
    iframe_html = driver.page_source
    driver.quit()
except Exception as e:
    logging.error(f"Error al cargar la página con Selenium: {e}")
    raise

try:
    # Guardar el contenido del iframe en un archivo code_iframe.txt
    with open('code_iframe.txt', 'w', encoding='utf-8') as file:
        file.write(iframe_html)
    logging.info("El contenido del iframe se ha guardado en 'code_iframe.txt'.")
except Exception as e:
    logging.error(f"Error al guardar el contenido del iframe en el archivo: {e}")
    raise

# Procesar el fichero code_iframe.txt para extraer información y generar el fichero eventos.csv
try:
    with open('code_iframe.txt', 'r', encoding='utf-8') as file:
        iframe_html = file.read()

    soup = BeautifulSoup(iframe_html, 'html.parser')
    table = soup.find('table', {'id': 'tablaEventos'})

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

        # Procesar cada enlace de Acestream
        for evento_acestream in eventos_acestream:
            nombre_canal = evento_acestream.text.strip()
            url_acestream = evento_acestream['href'].replace('acestream://', '')
            eventos.append([hora, competicion, evento, nombre_canal, url_acestream])

    # Guardar los eventos en un archivo CSV
    with open('eventos.csv', 'w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Hora', 'Competicion', 'Evento', 'Canales', 'Eventos_Acestream'])
        writer.writerows(eventos)

    logging.info("El fichero eventos.csv se ha generado correctamente.")
except Exception as e:
    logging.error(f"Error al procesar el fichero code_iframe.txt: {e}")
    raise

print("El contenido de la página se ha guardado en 'code.txt' y el contenido del iframe se ha guardado en 'code_iframe.txt'. El fichero eventos.csv se ha generado correctamente.")
