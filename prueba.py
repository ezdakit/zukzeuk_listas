from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def fetch_final_content(url, iframe_id, timeout=20):
    service = Service('/usr/bin/chromedriver')  # Ruta predeterminada de ChromeDriver en Ubuntu
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)

    # Print del contenido inicial
    initial_content = driver.page_source
    print("Contenido inicial:")
    print(initial_content[:1000] + '...' if len(initial_content) > 1000 else initial_content)

    # Esperar a que el iframe esté presente
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.ID, iframe_id)))

    iframe = driver.find_element(By.ID, iframe_id)
    iframe_src = iframe.get_attribute('src')
    print(f"URL del iframe: {iframe_src}")

    driver.get(iframe_src)

    # Esperar a que el contenido del iframe se estabilice
    WebDriverWait(driver, timeout).until(lambda d: d.execute_script('return document.readyState') == 'complete')

    # Captura de pantalla para depuración
    driver.save_screenshot('final_screenshot.png')

    # Obtener el contenido final
    final_content = driver.page_source
    print("Contenido final:")
    print(final_content[:1000] + '...' if len(final_content) > 1000 else final_content)

    driver.quit()

if __name__ == "__main__":
    url = "http://127.0.0.1:43110/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie"
    iframe_id = "inner-iframe"  # ID del iframe que quieres monitorizar
    fetch_final_content(url, iframe_id)
