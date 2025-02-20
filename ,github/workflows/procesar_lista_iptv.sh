#!/bin/bash

# Descargar el archivo M3U
curl -o lista-ott.m3u https://proxy.zeronet.dev/1H3KoazXt2gCJgeD8673eFvQYXG7cbRddU/lista-ott.m3u

# Procesar el archivo para eliminar el texto desde " -->" hasta el final de la línea
sed 's/ -->.*//' lista-ott.m3u > lista-ott-procesada.m3u

# Crear el nuevo archivo con los valores separados por comas
output_file="lista-ott-final.csv"
<BLOCKQUOTE><P>"$output_file"</P></BLOCKQUOTE>

# Leer el archivo procesado línea por línea
while IFS= read -r line; do
    # Buscar líneas que contengan el tag tvg-id
    if [[ $line == *tvg-id* ]]; then
        # Extraer los valores
        tvg_id=$(echo "$line" | sed -n 's/.*tvg-id="\([^"]*\)".*/\1/p')
        group_title=$(echo "$line" | sed -n 's/.*group-title="\([^"]*\)".*/\1/p')
        value3=$(echo "$line" | sed -n 's/.*, \(.*\)/\1/p')
        read -r next_line

        # Escribir los valores en el archivo de salida
        echo "$tvg_id,$group_title,$value3,$next_line" >> "$output_file"
    fi
done < lista-ott-procesada.m3u

echo "Procesamiento completado. El archivo final se ha guardado como $output_file"
