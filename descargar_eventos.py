import cloudscraper
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
import time
import csv
from bs4 import BeautifulSoup
import os

# Eliminar el archivo debug_eventos.txt si existe
if os.path.exists('debug_eventos.txt'):
    os.remove('debug_eventos.txt')

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
    time.sleep(10)

    # Esperar a que desaparezca el elemento de carga con texto "Cargando datos..."
    WebDriverWait(driver, 30).until(EC.invisibility_of_element_located((By.XPATH, "//*[contains(text(), 'Cargando datos...')]")))

    # Esperar a que la tabla esté visible
    WebDriverWait(driver, 30).until(EC.visibility_of_element_located((By.ID, 'tablaEventos')))

    # Obtener el contenido del iframe
    iframe_html = driver.page_source

    # Guardar el contenido del iframe en un archivo code_iframe.txt
    with open('code_iframe.txt', 'w', encoding='utf-8') as file:
        file.write(iframe_html)
    logging.info("El contenido del iframe se ha guardado en 'code_iframe.txt'.")

    driver.quit()
except Exception as e:
    logging.error(f"Error al cargar la página con Selenium: {e}")
    raise

try:
    # Analizar el contenido HTML del iframe
    soup = BeautifulSoup(iframe_html, 'html.parser')
    logging.info("Contenido HTML del iframe analizado correctamente.")

    # Encontrar la tabla en el iframe
    table = soup.find('table', {'id': 'tablaEventos'})
    if table is None:
        raise ValueError("No se encontró la tabla en el iframe.")
    logging.info("Tabla encontrada en el iframe.")

    # Extraer los encabezados de la tabla
    headers = [header.text.strip() for header in table.find_all('th')]
    logging.info("Encabezados de la tabla extraídos correctamente.")

    # Extraer las filas de la tabla
    rows = []
    for row in table.find('tbody').find_all('tr'):
        cells = [cell.text.strip() for cell in row.find_all('td')]
        rows.append(cells)
    logging.info("Filas de la tabla extraídas correctamente.")

    # Eliminar registros anteriores en eventos.csv
    open('eventos.csv', 'w').close()
    logging.info("Registros anteriores en 'eventos.csv' eliminados.")

    # Guardar el contenido de la tabla en un archivo CSV
    with open('eventos.csv', 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # Escribir los encabezados, excluyendo la columna "Canales"
        writer.writerow([headers, headers, headers, headers])

        for row in rows:
            hora = row
            competicion = row
            evento = row
            eventos_acestream = row

            # Analizar los hipervínculos en el campo "Eventos Acestream"
            soup_acestream = BeautifulSoup(eventos_acestream, 'html.parser')
            links = soup_acestream.find_all('a')

            for link in links:
                texto_mostrar = link.text.strip()
                url_acestream = link['href'].replace('acestream://', '')
                writer.writerow([hora, competicion, evento, f"{texto_mostrar} ({url_acestream})"])
    logging.info("El contenido de la tabla se ha guardado en 'eventos.csv'.")
except Exception as e:
    logging.error(f"Error al analizar el contenido del iframe: {e}")
    raise

print("El contenido de la tabla se ha guardado en 'eventos.csv'")
print("El contenido del iframe se ha guardado en 'code_iframe.txt'")
