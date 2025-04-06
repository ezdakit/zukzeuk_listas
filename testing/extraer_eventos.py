from bs4 import BeautifulSoup
import csv
import re

# Leer el archivo HTML
with open('testing/testing/new_all.txt', 'r', encoding='utf-8') as file:
    html_content = file.read()

soup = BeautifulSoup(html_content, 'html.parser')

# Encontrar todas las secciones de agenda deportiva
agenda_sections = soup.find_all('div', class_='tab-content', id='agendaTab')

# Preparar datos para CSV
csv_data = []

for section in agenda_sections:
    # Encontrar todas las tablas de eventos
    event_tables = section.find_all('table', class_='agenda-table')
    
    for table in event_tables:
        # Extraer la fecha del título
        date_match = re.search(r'Eventos deportivos - (\d{2}/\d{2}/\d{4})', table.get_text())
        if not date_match:
            continue
            
        date = date_match.group(1)
        
        # Encontrar todas las filas de eventos
        event_rows = table.find_all('tr', attrs={"data-event-id": True})
        
        for row in event_rows:
            event_id = row['data-event-id']
            
            # Buscar todos los enlaces de Acestream en esta fila
            stream_links = row.find_all('a', class_='stream-link', 
                                      onclick=re.compile(r"window\.openAcestream\('([a-f0-9]+)'\)"))
            
            for link in stream_links:
                # Extraer el ID de Acestream del onclick
                acestream_id = re.search(r"window\.openAcestream\('([a-f0-9]+)'\)", 
                                        link['onclick']).group(1)
                
                # Añadir al conjunto de datos
                csv_data.append({
                    'date': date,
                    'event_id': event_id,
                    'acestream_id': acestream_id
                })

# Escribir el archivo CSV
if csv_data:
    with open('eventos_acestream.csv', 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['date', 'event_id', 'acestream_id']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for row in csv_data:
            writer.writerow(row)
    print("Archivo CSV creado exitosamente: eventos_acestream.csv")
else:
    print("No se encontraron eventos con IDs de Acestream")
