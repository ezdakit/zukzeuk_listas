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

# Configuración de logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
file_handler = logging.FileHandler('debug_eventos.txt')
console_handler = logging.StreamHandler()
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Función para comparar dos archivos
def archivos_son_identicos(archivo1, archivo2):
    try:
        with open(archivo1, 'r') as f1, open(archivo2, 'r') as f2:
            return f1.read() == f2.read()
    except FileNotFoundError as e:
        logging.error(f"Error al abrir los archivos: {e}")
        sys.exit(1)  # Termina el script si no se pueden abrir los archivos

# Configuración de logging
# logging.basicConfig(filename='debug_eventos.txt', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

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
    logger.info("Solicitud HTTP exitosa.")
except cloudscraper.exceptions.CloudflareChallengeError as e:
    logger.error(f"Error en la solicitud HTTP: {e}")
    raise
except requests.exceptions.RequestException as e:
    logger.error(f"La URL no está disponible o hubo un error en la solicitud: {e}")
    sys.exit(1)  # Termina el script con un código de error
except ReadTimeoutError as e:
    logger.error(f"Tiempo de espera agotado: {e}")
    sys.exit(1)  # Termina el script con un código de error

try:
    # Configurar Selenium para cargar el contenido dinámico
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Ejecutar Chrome en modo headless
    options.add_argument("--user-data-dir=/tmp/selenium_chrome_user_data_unique")

    driver = webdriver.Chrome(options=options)
    driver.get(url)

    # Aumentar el tiempo de espera a 30 segundos
    WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
    logger.info("Contenido de la página cargado correctamente.")

    # Obtener el contenido de la página principal
    html_main = driver.page_source

    # Guardar el contenido de la página principal en un archivo code.txt
    with open('code.txt', 'w', encoding='utf-8') as file:
        file.write(html_main)
    logger.info("El contenido de la página principal se ha guardado en 'code.txt'.")

    try:
        WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, 'iframe')))
        driver.switch_to.frame(driver.find_element(By.TAG_NAME, 'iframe'))
        time.sleep(60)
        iframe_html = driver.page_source
        if "Not Found" in iframe_html:
            logger.error("El contenido del iframe no se cargó correctamente.")
        else:
            with open('code_iframe.txt', 'w', encoding='utf-8') as file:
                file.write(iframe_html)
            logger.info("El contenido del iframe se ha guardado en 'code_iframe.txt'.")
        driver.quit()
    except Exception as e:
        logger.error(f"Error al cargar el iframe: {e}")
   
except Exception as e:
    logger.error(f"Error al cargar la página con Selenium: {e}")
    raise

print("Proceso completado.")
