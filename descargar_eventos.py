import cloudscraper
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging

# Configuración de logging
logging.basicConfig(filename='debug_eventos.txt', level=logging.DEBUG, format='%(asctime)s - %(levellevelname)s - %(message)s')

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

    # Esperar a que desaparezca el elemento de carga con texto "Cargando datos..."
    WebDriverWait(driver, 30).until(EC.invisibility_of_element_located((By.XPATH, "//*[contains(text(), 'Cargando datos...')]")))

    # Esperar a que la tabla esté visible
    WebDriverWait(driver, 30).until(EC.visibility_of_element_located((By.ID, 'tablaEventos')))

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

print("El contenido de la página se ha guardado en 'code.txt' y el contenido del iframe se ha guardado en 'code_iframe.txt'")
