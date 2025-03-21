from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import difflib

def fetch_final_content(url, iframe_id, timeout=5, max_duration=60):
    service = Service('/usr/bin/chromedriver')  # Ruta predeterminada de ChromeDriver en Ubuntu
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)

    # Print del contenido inicial
    initial_content = driver.page_source
    print("Contenido inicial:")
    print(initial_content)

    # Esperar a que el iframe esté presente
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, iframe_id)))

    iframe = driver.find_element(By.ID, iframe_id)
    iframe_src = iframe.get_attribute('src')
    print(f"URL del iframe: {iframe_src}")

    driver.get(iframe_src)

    previous_content = driver.page_source
    start_time = time.time()
    max_time = start_time + max_duration
    exit_reason = None

    while time.time() < max_time:
        current_content = driver.page_source

        # Espera explícita para contenido dinámico
        WebDriverWait(driver, timeout).until(lambda d: d.page_source != previous_content)

        # Prints para depuración
        print(f"Tiempo actual: {time.time()}")
        if previous_content is not None:
            diff = difflib.unified_diff(previous_content.splitlines(), current_content.splitlines(), lineterm='')
            diff_text = '\n'.join(diff)
            print("Diferencias entre contenido anterior y actual (limitadas a 100 caracteres):")
            print(diff_text[:100] + '...' if len(diff_text) > 100 else diff_text)
        else:
            print("Contenido anterior: None")

        print(f"Tiempo desde última actualización: {time.time() - start_time}")

        if current_content != previous_content:
            previous_content = current_content
            start_time = time.time()
            print("Contenido actualizado, reiniciando temporizador.")
        elif time.time() - start_time >= timeout:
            exit_reason = "timeout"
            print("Contenido no ha cambiado en el tiempo especificado, saliendo del bucle.")
            break

        time.sleep(1)

    if exit_reason is None:
        exit_reason = "max_duration"

    print("Contenido final:")
    print(current_content)
    print(f"Razón de salida del bucle: {exit_reason}")

    driver.quit()

if __name__ == "__main__":
    url = "http://127.0.0.1:43110/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie"
    iframe_id = "inner-iframe"  # ID del iframe que quieres monitorizar
    fetch_final_content(url, iframe_id)
