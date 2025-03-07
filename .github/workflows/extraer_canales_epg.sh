#!/bin/bash

# Renombrar el archivo canales.txt existente a canales_prev.txt
if [ -f canales.txt ]; then
    mv canales.txt canales_prev.txt
fi

# Descargar el archivo XML
curl -o guiatv.xml https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml

# Extraer el texto de las etiquetas <channel id="..."> y guardarlo en canales.txt
sed -n 's/.*<channel id="\([^"]*\)">.*/\1/p' guiatv.xml > canales.txt

# Generar un tercer archivo canales_nuevos.txt con las líneas nuevas de canales.txt que no están en canales_prev.txt
if [ -f canales_prev.txt ]; then
    grep -Fxv -f canales_prev.txt canales.txt > canales_nuevos.txt
else
    cp canales.txt canales_nuevos.txt
fi

echo "Extracción completada. Los canales se han guardado en canales.txt y los nuevos canales en canales_nuevos.txt"
