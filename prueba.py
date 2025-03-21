import os
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import subprocess

def fetch_bridges():
    response = requests.get('https://bridges.torproject.org/bridges?transport=obfs4')
    if response.status_code == 200:
        bridges = response.text.split('\n')
        return bridges
    else:
        print("Error fetching bridges")
        return []

def fetch_final_content(url, iframe_id, timeout=20):
    service = Service('/usr/bin/chromedriver') # Ruta predeterminada de ChromeDriver en Ubuntu
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)

    # Crear carpeta "pantallazos" si no existe
    if not os.path.exists('pantallazos'):
        os.makedirs('pantallazos')
    
    # Borrar todo el contenido de la carpeta "pantallazos"
    for file in os.listdir('pantallazos'):
        file_path = os.path.join('pantallazos', file)
        if os.path.isfile(file_path):
            os.unlink(file_path)

    # Print del contenido inicial
    initial_content = driver.page_source
    print("Contenido inicial:")
    print(initial_content[:1000] + '...' if len(initial_content) > 1000 else initial_content)

    # Captura de pantalla inicial
    driver.save_screenshot('pantallazos/screenshot_initial.png')

    # Capturar pantalla cada medio segundo hasta que el iframe esté presente
    start_time = time.time()
    screenshot_counter = 1
    while time.time() - start_time < timeout:
        driver.save_screenshot(f'pantallazos/screenshot_{screenshot_counter}.png')
        screenshot_counter += 1
        try:
            iframe = driver.find_element(By.ID, iframe_id)
            break
        except:
            time.sleep(0.5)

    iframe_src = iframe.get_attribute('src')
    print(f"URL del iframe: {iframe_src}")
    driver.get(iframe_src)

    # Esperar a que el contenido del iframe se estabilice y capturar pantalla cada medio segundo
    start_time = time.time()
    while time.time() - start_time < timeout:
        driver.save_screenshot(f'pantallazos/screenshot_iframe_{screenshot_counter}.png')
        screenshot_counter += 1
        if driver.execute_script('return document.readyState') == 'complete':
            break
        time.sleep(0.5)

    # Captura de pantalla final para depuración
    driver.save_screenshot('pantallazos/final_screenshot.png')

    # Obtener el contenido final
    final_content = driver.page_source
    print("Contenido final:")
    print(final_content[:1000] + '...' if len(final_content) > 1000 else final_content)

    driver.quit()

if __name__ == "__main__":
    url = "http://127.0.0.1:43110/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie"
    iframe_id = "inner-iframe" # ID del iframe que quieres monitorizar
    bridges = fetch_bridges()
    if bridges:
        with open('torrc_temp', 'w') as torrc:
            torrc.write("UseBridges 1\n")
            torrc.write("ClientTransportPlugin obfs4 exec /usr/bin/obfs4proxy\n")
            for bridge in bridges:
                torrc.write(f"Bridge obfs4 {bridge}\n")
                print(f"Bridge configured: {bridge}")
        subprocess.run(['sudo', 'mv', 'torrc_temp', '/etc/tor/torrc'])
        subprocess.run(['sudo', 'service', 'tor', 'restart'])
    
    fetch_final_content(url, iframe_id)
    
    # Collect ZeroNet logs and ensure they are not empty
    result = subprocess.run(['docker', 'logs', 'zeronet'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with open('zeronet_logs.txt', 'w') as log_file:
        log_file.write(result.stdout.decode())
        log_file.write(result.stderr.decode())
