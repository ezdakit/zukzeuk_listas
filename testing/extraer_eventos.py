from bs4 import BeautifulSoup
import csv
import re

with open('testing/testing/new_all.txt', 'r', encoding='utf-8') as file:
    soup = BeautifulSoup(file.read(), 'html.parser')

csv_data = []

# Buscar el contenedor de eventos
events_container = soup.find('div', id='eventsContainer')
if not events_container:
    print("No se encontró el contenedor de eventos (div#eventsContainer)")
    exit()

# Procesar cada día de eventos
for day in events_container.find_all('div', class_='events-day'):
    # Extraer fecha del atributo data-date o del texto h2
    date_from_attr = day.get('data-date', '')
    date_from_text = re.search(r'(\d{2}/\d{2}/\d{4})', day.h2.get_text() if day.h2 else '')
    
    date = date_from_attr if date_from_attr else (date_from_text.group(1) if date_from_text else 'Fecha desconocida')
    
    # Procesar tabla de eventos
    table = day.find('table', class_='events-table')
    if not table:
        continue
    
    # Buscar filas del cuerpo de la tabla (omitir encabezados)
    for row in table.find_all('tr')[1:]:  # Saltar la primera fila (thead)
        # Extraer información básica
        cols = row.find_all('td')
        if len(cols) < 4:  # Debe tener al menos 4 columnas según la estructura
            continue
        
        time = cols[0].get_text(strip=True)
        competition = cols[1].get_text(strip=True)
        match = cols[2].get_text(strip=True)
        
        # Crear event_id combinando información relevante
        event_id = f"{time}-{competition}-{match}".replace(" ", "_")
        
        # Buscar enlaces de Acestream en la columna de canales
        for link in cols[3].find_all('a', onclick=re.compile(r"openAcestream\('([a-f0-9]+)'")):
            acestream_id = re.search(r"openAcestream\('([a-f0-9]+)'", link['onclick']).group(1)
            csv_data.append({
                'date': date,
                'event_id': event_id,
                'acestream_id': acestream_id,
                'time': time,
                'competition': competition,
                'match': match
            })

# Escribir el archivo CSV
if csv_data:
    with open('testing/testing/eventos_acestream.csv', 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['date', 'event_id', 'acestream_id', 'time', 'competition', 'match']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        writer.writerows(csv_data)
    print(f"Archivo CSV creado exitosamente con {len(csv_data)} eventos.")
else:
    print("No se encontraron eventos con IDs de Acestream. Revisa:")
    print("- Que existan enlaces con onclick=\"openAcestream('ID')\" en la columna 'Canales'")
    print("- Que la estructura de la tabla coincida con lo esperado")
