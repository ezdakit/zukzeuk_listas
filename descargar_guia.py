import requests
import re
import os

# Borrar el archivo canales_nuevos.txt si existe
if os.path.exists("canales_nuevos.txt"):
    os.remove("canales_nuevos.txt")

# Renombrar el archivo canales.txt existente a canales_prev.txt
if os.path.exists("canales.txt"):
    os.rename("canales.txt", "canales_prev.txt")
else:
    with open("canales_prev.txt", "w") as file:
        pass  # Crear un archivo vacío

# Descargar el archivo XML
url = "https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml"
response = requests.get(url)
with open("guiatv.xml", "w") as file:
    file.write(response.text)

# Extraer el texto de las etiquetas <channel id="..."> y guardarlo en canales.txt
with open("guiatv.xml", "r") as file_xml, open("canales.txt", "w") as file_txt:
    for line in file_xml:
        match = re.search(r'<channel id="([^"]*)">', line)
        if match:
            file_txt.write(match.group(1) + "\n")

# Generar un tercer archivo canales_nuevos.txt con las líneas nuevas de canales.txt que no están en canales_prev.txt
if os.path.exists("canales_prev.txt"):
    with open("canales_prev.txt", "r") as file_prev, open("canales.txt", "r") as file_actual:
        canales_prev = set(file_prev.readlines())
        canales_actual = set(file_actual.readlines())
    nuevos_canales = canales_actual - canales_prev
    if nuevos_canales:
        with open("canales_nuevos.txt", "w") as file_nuevos:
            for canal in nuevos_canales:
                file_nuevos.write(canal)

print("Extracción completada. Los canales se han guardado en canales.txt y los nuevos canales en canales_nuevos.txt (si hay diferencias).")
