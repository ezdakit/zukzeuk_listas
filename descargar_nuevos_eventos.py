# Procesar el fichero eventos.csv para generar zz_eventos_ott.m3u
try:
    # Ruta del archivo eventos.csv
    input_csv = 'eventos.csv'
    # Ruta del archivo de salida zz_eventos_ott.m3u
    output_m3u = 'zz_eventos_ott.m3u'

    # Cabecera del archivo M3U
    m3u_header = """#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml"
#EXTVLCOPT:network-caching=2000

"""

    # Abrir el archivo CSV para lectura
    with open(input_csv, 'r', encoding='utf-8') as csv_file:
        csv_reader = csv.reader(csv_file)
        next(csv_reader)  # Saltar la primera fila (encabezados)

        # Abrir el archivo M3U para escritura
        with open(output_m3u, 'w', encoding='utf-8') as m3u_file:
            # Escribir la cabecera del archivo M3U
            m3u_file.write(m3u_header)

            # Procesar cada línea del CSV
            for row in csv_reader:
                hora, competicion, evento, nombre_canal, eventos_acestream = row

                # Crear la línea #EXTINF con "Evento: " en group-title
                extinf_line = f'#EXTINF:-1 tvg-id="" group-title="Evento: {competicion}", {hora} {evento}\n'

                # Crear la línea de la URL
                url_line = f'http://127.0.0.1:6878/ace/getstream?id={eventos_acestream}\n'

                # Escribir ambas líneas en el archivo M3U
                m3u_file.write(extinf_line)
                m3u_file.write(url_line)

    logging.info("El archivo zz_eventos_ott.m3u se ha generado correctamente.")
except Exception as e:
    logging.error(f"Error al procesar el archivo CSV o generar el archivo M3U: {e}")
    raise
