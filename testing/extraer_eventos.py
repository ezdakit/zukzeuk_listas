from bs4 import BeautifulSoup
import csv
import re

def format_match_info(match_cell):
    """Formatea correctamente la información del partido, manteniendo espacios entre elementos span"""
    match_info = match_cell.find('div', class_='match-info')
    if match_info:
        # Extraer texto preservando espacios entre elementos
        parts = []
        for element in match_info.find_all(['span', 'img']):
            if element.name == 'span':
                parts.append(element.get_text(strip=True))
            elif 'vs-text' in element.get('class', []):
                parts.append(' vs ')  # Mantener espacios alrededor del "vs"
        
        return ' '.join(parts).replace('  ', ' ').strip()
    else:
        # Si no hay match-info, usar el texto normal
        return match_cell.get_text(' ', strip=True)

def format_competition_info(competition_cell):
    """Formatea correctamente la información de la competición, combinando nombre y fase"""
    competition_info = competition_cell.find('div', class_='competition-info')
    if competition_info:
        name = competition_info.find('span', class_='competition-name')
        fase = competition_info.find('div', class_='fase')
        
        name_text = name.get_text(strip=True) if name else ''
        fase_text = fase.get_text(strip=True) if fase else ''
        
        # Combinar con un espacio si ambos existen
        if name_text and fase_text:
            return f"{name_text} {fase_text}"
        else:
            return name_text or fase_text
    else:
        return competition_cell.get_text(' ', strip=True)

def replace_commas_with_dots(data):
    """Reemplaza comas por puntos en todos los campos de un diccionario"""
    for key in data:
        if isinstance(data[key], str):
            data[key] = data[key].replace(",", ".")
    return data

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
        competition = format_competition_info(cols[1])  # Usamos la nueva función de formateo
        match = format_match_info(cols[2])
        
        # Crear un event_id más descriptivo si el actual es genérico
        if event_id.endswith('--'):
            teams = match.split(' vs ') if ' vs ' in match else [match]
            event_id = f"{time}-{'-'.join([t.strip() for t in teams])}"
        
        # Procesar los grupos de streams
        for group in detail_row.find_all('div', class_='stream-channel-group'):
            group_name = group.find('h4').get_text(strip=True) if group.find('h4') else 'Sin grupo'
            
            # Buscar todos los enlaces de Acestream en este grupo
            for link in group.find_all('a', class_='stream-link', 
                                     onclick=re.compile(r"openAcestream\('([a-f0-9]+)'")):
                acestream_id = re.search(r"openAcestream\('([a-f0-9]+)'", link['onclick']).group(1)
                
                # Determinar calidad (FHD, SD, etc.)
                quality = 'FHD' if 'FHD' in link.get_text() else ('SD' if 'SD' in link.get_text() else '')
                
                # Crear el diccionario y reemplazar comas por puntos
                entry = {
                    'date': date,
                    'event_id': event_id,
                    'time': time,
                    'competition': competition,
                    'match': match,
                    'group': group_name,
                    'acestream_id': acestream_id,
                    'quality': quality
                }
                csv_data.append(replace_commas_with_dots(entry))

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
