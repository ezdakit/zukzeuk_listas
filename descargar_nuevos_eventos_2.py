import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# URL de la página principal
url = 'http://127.0.0.1:43110/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie'

try:
    # Configurar Selenium para cargar el contenido dinámico
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Ejecutar Chrome en modo headless
    options.add_argument("--user-data-dir=/tmp/selenium_chrome_user_data_unique")

    # Inicializar el driver de Chrome
    driver = webdriver.Chrome(options=options)
    driver.get(url)

    # Esperar a que la página principal esté completamente cargada
    WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
    logger.info("Contenido de la página principal cargado correctamente.")

    # Esperar a que el iframe esté presente
    WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, 'iframe')))
    logger.info("Iframe detectado en la página principal.")

    # Obtener la URL del iframe
    iframe = driver.find_element(By.TAG_NAME, 'iframe')
    iframe_src = iframe.get_attribute('src')
    logger.info(f"URL del iframe: {iframe_src}")

    # Verificar si la URL del iframe es válida
    if not iframe_src:
        raise ValueError("La URL del iframe está vacía o no es válida.")

    # Abrir la URL del iframe en una nueva pestaña
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[1])
    driver.get(iframe_src)

    # Esperar a que el contenido del iframe se cargue
    WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
    logger.info("Contenido del iframe cargado correctamente.")

    # Esperar a que la tabla esté presente
    WebDriverWait(driver, 60).until(
        EC.presence_of_element_located((By.XPATH, "//table//tr"))
    )
    logger.info("Tabla detectada en el iframe.")

    # Capturar el contenido del iframe
    iframe_html = driver.page_source
    logger.info("Contenido del iframe capturado correctamente.")

    # Guardar el contenido del iframe en un archivo
    with open('code_iframe.txt', 'w', encoding='utf-8') as file:
        file.write(iframe_html)
    logger.info("El contenido del iframe se ha guardado en 'code_iframe.txt'.")

except Exception as e:
    logger.error(f"Error durante la ejecución del script: {e}")

finally:
    # Cerrar el navegador
    if driver:
        driver.quit()
    logger.info("Navegador cerrado.")
