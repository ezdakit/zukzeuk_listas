from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import csv
import re
import logging

# Configuración de logging
logging.basicConfig(filename='debug_eventos.txt', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# URL de la página web
url = 'https://proxy.zeronet.dev/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie'

try:
    # Configurar el navegador con un directorio de datos único
    options = webdriver.ChromeOptions()
    options.add_argument("--user-data-dir=/tmp/selenium_chrome_user_data")

    driver = webdriver.Chrome(options=options)  # Asegúrate de tener el controlador de Chrome instalado
    driver.get(url)

    # Esperar a que la tabla se cargue
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
    logging.info("Tabla encontrada en la página web.")

    # Obtener el contenido de la página
    html = driver.page_source
    driver.quit()
except Exception as e:
    logging.error(f"Error al cargar la página con Selenium: {e}")
    raise

try:
    # Analizar el contenido HTML de la página web
    soup = BeautifulSoup(html, 'html.parser')
    logging.info("Contenido HTML analizado correctamente.")
except Exception as e:
    logging.error(f"Error al analizar el contenido HTML: {e}")
    raise

try:
    # Encontrar la tabla en la página web
    table = soup.find('table')
    if table is None:
        raise ValueError("No se encontró la tabla en la página web.")
    logging.info("Tabla encontrada en la página web.")
except Exception as e:
    logging.error(f"Error al encontrar la tabla: {e}")
    raise

try:
    # Extraer los encabezados de la tabla
    headers = [header.text for header in table.find_all('th')]
    logging.info("Encabezados de la tabla extraídos correctamente.")
except Exception as e:
    logging.error(f"Error al extraer los encabezados de la tabla: {e}")
    raise

# Función para eliminar emoticonos
def remove_emojis(text):
    emoji_pattern = re.compile("["
                           u"\U0001F600-\U0001F64F"  # emoticonos
                           u"\U0001F300-\U0001F5FF"  # símbolos y pictogramas
                           u"\U0001F680-\U0001F6FF"  # transporte y símbolos de mapa
                           u"\U0001F1E0-\U0001F1FF"  # banderas (iOS)
                           "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text)

try:
    # Extraer las filas de la tabla
    rows = []
    for row in table.find_all('tr')[1:]:  # Omitir el encabezado
        cells = []
        for i, cell in enumerate(row.find_all('td')):
            if i == 1 or i == 2:  # Columnas "Competición" y "Evento"
                text = remove_emojis(cell.text)
                cells.append(text)
            elif cell.find('a'):  # Si la celda contiene un hipervínculo
                links = cell.find_all('a')
                link_texts = [f"{link.text} ({link['href'].replace('acestream://', '')})" for link in links]
                cells.append(' | '.join(link_texts))
            else:
                cells.append(cell.text)
        rows.append(cells)
    logging.info("Filas de la tabla extraídas correctamente.")
except Exception as e:
    logging.error(f"Error al extraer las filas de la tabla: {e}")
    raise

try:
    # Guardar el contenido de la tabla en un archivo CSV
    with open('eventos.csv', 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(headers)  # Escribir los encabezados
        writer.writerows(rows)    # Escribir las filas
    logging.info("El contenido de la tabla se ha guardado en 'eventos.csv'.")
except Exception as e:
    logging.error(f"Error al guardar el contenido de la tabla en el archivo CSV: {e}")
    raise

print("El contenido de la tabla se ha guardado en 'eventos.csv'")
