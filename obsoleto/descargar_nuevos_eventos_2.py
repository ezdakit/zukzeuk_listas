import time
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# URL del iframe
iframe_src = 'http://127.0.0.1:43110/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie/?wrapper_nonce=36c675088d663a7f4bc575928f5924ff5bdc2301b739cfc3c752b6d91dbbe011'

# Inicializar driver como None para manejar excepciones
driver = None

try:
    # Comprobar si hay instancias de Chrome en ejecución y terminarlas
    logger.info("Comprobando si hay instancias de Chrome en ejecución...")
    chrome_processes = subprocess.run(["pgrep", "-f", "chrome"], stdout=subprocess.PIPE)
    if chrome_processes.returncode == 0:  # Si se encontraron procesos de Chrome
        logger.info("Instancias de Chrome en ejecución encontradas. Terminándolas...")
        subprocess.run(["pkill", "-f", "chrome"])
        time.sleep(2)  # Esperar un poco para que los procesos se terminen

    # Configurar Selenium para cargar el contenido dinámico con Chrome
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")  # Comenta esta línea para desactivar el modo headless
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--enable-javascript")
    options.add_argument("--disable-web-security")  # Deshabilitar políticas de seguridad
    options.add_argument("--disable-xss-auditor")  # Deshabilitar auditoría XSS

    # Configurar User-Agent
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.117 Safari/537.36"
    options.add_argument(f"user-agent={user_agent}")

    # Configurar logs del navegador
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

    # Inicializar el driver de Chrome
    driver = webdriver.Chrome(options=options)

    # Abrir la URL del iframe
    logger.info(f"Abriendo directamente la URL del iframe: {iframe_src}")
    driver.get(iframe_src)

    # Esperar a que el contenido del iframe se cargue
    WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
    logger.info("Contenido del iframe cargado correctamente.")

    # Esperar a que la tabla esté presente
    try:
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.XPATH, "//table//tr"))
        )
        logger.info("Tabla detectada en el iframe.")
    except Exception as e:
        logger.error(f"Error al buscar la tabla en el iframe: {e}")

    # Capturar el contenido del iframe
    iframe_html = driver.page_source
    logger.info(f"Contenido del iframe: {iframe_html}")  # Imprime el contenido para depuración

    # Guardar el contenido del iframe en un archivo
    with open('code_iframe.txt', 'w', encoding='utf-8') as file:
        file.write(iframe_html)
    logger.info("El contenido del iframe se ha guardado en 'code_iframe.txt'.")

    # Capturar y mostrar los logs del navegador
    logs = driver.get_log('browser')
    logger.info("Capturando logs del navegador...")
    for log in logs:
        logger.info(f"Log del navegador: {log}")

except Exception as e:
    logger.error(f"Error durante la ejecución del script: {e}")

finally:
    # Cerrar el navegador si el driver está definido
    if driver:
        driver.quit()
        logger.info("Navegador cerrado.")
