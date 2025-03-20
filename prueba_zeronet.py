import requests
from bs4 import BeautifulSoup
import time

def get_zeronet_content(url):
    """Descarga el contenido de una URL de ZeroNet."""
    try:
        response = requests.get(url)
        response.raise_for_status()  # Lanza una excepción para códigos de error (4xx o 5xx)
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error al descargar la URL: {e}")
        return None

def extract_iframe_content(html):
    """Extrae el contenido del iframe de una página HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    iframe = soup.find('iframe')
    if iframe:
        iframe_url = iframe['src']
        # Si el iframe es una URL relativa, puedes necesitar reconstruir la URL completa
        if not iframe_url.startswith('http'):
          base_url = "http://127.0.0.1:43110/"
          iframe_url = base_url + iframe_url
        iframe_content = get_zeronet_content(iframe_url)
        if iframe_content:
            iframe_soup = BeautifulSoup(iframe_content, 'html.parser')
            table = iframe_soup.find('table') #busca una tabla dentro del iframe, esto es opcional.
            if table:
              return iframe_content
            else:
              return "Error: No se encontró una tabla en el iframe."
        else:
            return "Error: No se pudo descargar el contenido del iframe."
    else:
        return "Error: No se encontró un iframe en la página."

if __name__ == "__main__":
    zeronet_url = "http://127.0.0.1:43110/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie" # Reemplaza con tu URL de ZeroNet
    html_content = get_zeronet_content(zeronet_url)

    if html_content:
        iframe_text = extract_iframe_content(html_content)
        if iframe_text:
          with open("iframe_content.txt", "w") as f:
              f.write(iframe_text)
          print("Contenido del iframe guardado en iframe_content.txt")
        else:
          print ("No se ha podido extraer el contenido del iframe")
    else:
        print("No se pudo descargar el contenido de la página principal de ZeroNet.")
