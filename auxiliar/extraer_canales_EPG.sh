#!/bin/bash

# Obtener la fecha actual en el formato XXYYZZ
fecha=$(date +'%y%m%d')

# Comprobar si el archivo canales.txt existe y renombrarlo
if [ -f canales.txt ]; then
    mv canales.txt "canales-$fecha.txt"
fi

# Descargar el archivo XML
curl -o guiatv.xml https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml

# Extraer el texto de las etiquetas <channel id="..."> y guardarlo en canales.txt
sed -n 's/.*<channel id="\([^"]*\)">.*/\1/p' guiatv.xml > canales.txt

echo "Extracción completada. Los canales se han guardado en canales.txt"
