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
    
    # Buscar todas las filas de evento principal (event-row)
    for event_row in day.find_all('tr', class_='event-row'):
        event_id = event_row.get('data-event-id', '')
        
        # Buscar la fila de detalles correspondiente (mismo data-event-id)
        detail_row = day.find('tr', class_='event-detail', attrs={'data-event-id': event_id})
        if not detail_row:
            continue  # Si no hay fila de detalles, saltar este evento
        
        # Extraer información básica del evento
        cols = event_row.find_all('td')
        if len(cols) < 4:
            continue
        
        time = cols[0].get_text(strip=True)
        competition = cols[1].get_text(strip=True)
        match = cols[2].get_text(strip=True)
        
        # Procesar los grupos de streams
        for group in detail_row.find_all('div', class_='stream-channel-group'):
            group_name = group.find('h4').get_text(strip=True) if group.find('h4') else 'Sin grupo'
            
            # Buscar todos los enlaces de Acestream en este grupo
            for link in group.find_all('a', class_='stream-link', 
                                     onclick=re.compile(r"openAcestream\('([a-f0-9]+)'")):
                acestream_id = re.search(r"openAcestream\('([a-f0-9]+)'", link['onclick']).group(1)
                
                # Determinar calidad (FHD, SD, etc.)
                quality = 'FHD' if 'FHD' in link.get_text() else ('SD' if 'SD' in link.get_text() else '')
                
                csv_data.append({
                    'date': date,
                    'event_id': event_id,
                    'time': time,
                    'competition': competition,
                    'match': match,
                    'group': group_name,
                    'acestream_id': acestream_id,
                    'quality': quality
                })

# Escribir el archivo CSV
if csv_data:
    with open('testing/testing/eventos_acestream.csv', 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['date', 'event_id', 'time', 'competition', 'match', 'group', 'acestream_id', 'quality']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        writer.writerows(csv_data)
    print(f"Archivo CSV creado exitosamente con {len(csv_data)} entradas de Acestream.")
else:
    print("No se encontraron eventos con IDs de Acestream.")
