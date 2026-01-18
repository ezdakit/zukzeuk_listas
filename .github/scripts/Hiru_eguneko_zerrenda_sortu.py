#!/usr/bin/env python3
"""
Script para scrapear eventos deportivos desde IPFS y generar archivo M3U
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import os
import hashlib
from datetime import datetime
import time
import random

# Lista de gateways IPFS alternativos (más rápidos primero)
IPFS_GATEWAYS = [
    "https://cloudflare-ipfs.com",  # Muy rápido
    "https://cf-ipfs.com",          # Alternativa Cloudflare
    "https://ipfs.io",              # Oficial
    "https://dweb.link",            # Protocol Labs
    "https://gateway.ipfs.io",      # Oficial alternativo
    "https://ipfs.tech",            # Nuevo oficial
]

def get_ipfs_content(ipns_hash, path="", timeout=10):
    """
    Obtiene contenido desde IPNS usando gateways IPFS
    
    Args:
        ipns_hash: Hash IPNS
        path: Ruta adicional
        timeout: Tiempo máximo de espera
        
    Returns:
        Contenido HTML o None si falla
    """
    # Limpiar path
    if path.startswith('/'):
        path = path[1:]
    
    # Headers para evitar bloqueos
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    # Probar gateways en orden, parando al primero que funcione
    for gateway in IPFS_GATEWAYS:
        try:
            # Construir URL
            if path:
                url = f"{gateway}/ipns/{ipns_hash}/{path}"
            else:
                url = f"{gateway}/ipns/{ipns_hash}"
            
            print(f"Probando gateway: {gateway}")
            
            # Hacer la petición
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True
            )
            
            # Verificar respuesta
            if response.status_code == 200:
                # Verificar que sea HTML
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' in content_type or '<html' in response.text[:100].lower():
                    print(f"✓ Éxito con gateway: {gateway}")
                    print(f"URL accedida: {url}")
                    return response.text
                else:
                    print(f"✗ Contenido no HTML de gateway: {gateway}")
                    continue
            else:
                print(f"✗ Error HTTP {response.status_code} de gateway: {gateway}")
                continue
                
        except requests.exceptions.Timeout:
            print(f"✗ Timeout con gateway: {gateway}")
            continue
            
        except requests.exceptions.ConnectionError:
            print(f"✗ Error de conexión con gateway: {gateway}")
            continue
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Error con gateway {gateway}: {str(e)}")
            continue
    
    print("✗ Todos los gateways fallaron")
    return None

def extract_events_from_html(html_content):
    """
    Extrae eventos deportivos del HTML de la pestaña Agenda Deportiva
    
    Args:
        html_content: Contenido HTML de la página
        
    Returns:
        Lista de eventos con canales Acestream
    """
    if not html_content:
        print("✗ No hay contenido HTML para analizar")
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # DEBUG: Guardar HTML para análisis
    with open('debug_html.html', 'w', encoding='utf-8') as f:
        f.write(html_content[:50000])  # Solo primeros 50k caracteres
    
    # Buscar TODAS las pestañas para debug
    print("Buscando todas las pestañas...")
    all_tabs = soup.find_all('div', class_='tab-content')
    print(f"Tabs encontrados: {len(all_tabs)}")
    for i, tab in enumerate(all_tabs):
        tab_id = tab.get('id', f'sin_id_{i}')
        print(f"  Tab {i}: id='{tab_id}', clase='{tab.get('class', [])}'")
    
    # Buscar la pestaña de agenda deportiva - CORREGIDO
    # Según tu HTML, el ID es "agendaDeportivaTab" no "agendaTab"
    agenda_tab = soup.find('div', {'id': 'agendaDeportivaTab'})
    
    if not agenda_tab:
        print("✗ No se encontró la pestaña de agenda deportiva (agendaDeportivaTab)")
        # Intentar buscar por texto
        agenda_tab = soup.find('div', string=re.compile('agenda', re.IGNORECASE))
        if agenda_tab:
            print("✓ Encontrado por texto 'agenda'")
        else:
            # Buscar cualquier div con eventos
            agenda_tab = soup.find('div', class_=re.compile('agenda', re.IGNORECASE))
    
    if not agenda_tab:
        print("✗ No se encontró ningún elemento que parezca agenda deportiva")
        return events
    
    print("✓ Encontrada pestaña de agenda deportiva")
    
    # Buscar navegación de días (basado en tu HTML)
    print("Buscando navegación de días...")
    agenda_nav = agenda_tab.find('div', {'class': 'agenda-nav'})
    if agenda_nav:
        print("✓ Encontrada navegación de días")
        date_buttons = agenda_nav.find_all('button', {'class': 'date-btn'})
        print(f"  Botones de fecha: {len(date_buttons)}")
    else:
        print("✗ No se encontró navegación de días")
    
    # Buscar secciones de eventos por día
    # En tu HTML, cada día está en un div con clase 'events-day'
    day_sections = agenda_tab.find_all('div', {'class': 'events-day'})
    
    if not day_sections:
        # Buscar tablas directamente
        print("Buscando tablas de eventos...")
        events_tables = agenda_tab.find_all('table', {'class': 'events-table'})
        print(f"Tablas de eventos encontradas: {len(events_tables)}")
        
        # Si hay tablas, crear una sección por cada tabla
        for table in events_tables:
            # Intentar extraer fecha de la tabla
            date_text = "Hoy"
            prev_elem = table.find_previous(['h3', 'h4', 'div'])
            if prev_elem:
                date_text = prev_elem.text.strip()[:20]
            
            day_sections = [{'date': date_text, 'table': table}]
    else:
        print(f"Secciones de días encontradas: {len(day_sections)}")
    
    # Si aún no hay secciones, buscar cualquier tabla en agenda_tab
    if not day_sections:
        print("Buscando cualquier tabla en la agenda...")
        all_tables = agenda_tab.find_all('table')
        print(f"Tablas totales: {len(all_tables)}")
        
        for table in all_tables:
            day_sections = [{'date': 'Eventos', 'table': table}]
            break
    
    # Procesar cada sección/día
    for day_section in day_sections:
        if isinstance(day_section, dict):
            # Es un diccionario creado manualmente
            date_text = day_section.get('date', 'Sin fecha')
            events_table = day_section.get('table')
        else:
            # Es un elemento BeautifulSoup
            # Extraer fecha del día
            date_text = "Sin fecha"
            
            # Buscar fecha en diferentes estructuras
            date_elem = day_section.find(['h3', 'h4', 'div'], class_=lambda x: x and ('title' in str(x).lower() or 'date' in str(x).lower()))
            if date_elem:
                date_text = date_elem.text.strip()
            else:
                # Buscar cualquier texto que parezca fecha
                date_match = re.search(r'(\d{1,2})[-/](\d{1,2})', day_section.text)
                if date_match:
                    date_text = f"{date_match.group(1)}-{date_match.group(2)}"
            
            # Buscar tabla de eventos dentro de la sección
            events_table = day_section.find('table', {'class': 'events-table'})
            if not events_table:
                events_table = day_section.find('table')
        
        if not events_table:
            print(f"✗ No se encontró tabla para: {date_text}")
            continue
        
        # Parsear fecha
        formatted_date = parse_date(date_text)
        print(f"  Procesando fecha: {date_text} -> {formatted_date}")
        
        # Buscar filas de eventos
        event_rows = events_table.find_all('tr', {'class': 'event-row'})
        if not event_rows:
            # Buscar cualquier fila que tenga suficientes celdas
            all_rows = events_table.find_all('tr')
            event_rows = []
            for row in all_rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 3:  # Al menos hora, categoría, evento
                    event_rows.append(row)
        
        print(f"    Eventos encontrados en tabla: {len(event_rows)}")
        
        for row_idx, row in enumerate(event_rows):
            try:
                # Extraer información de la fila
                cells = row.find_all(['td', 'th'])
                if len(cells) < 3:
                    print(f"    Fila {row_idx}: Solo {len(cells)} celdas, saltando")
                    continue
                
                # Hora (asumimos primera celda)
                time_str = cells[0].text.strip()
                print(f"    Fila {row_idx}: Hora='{time_str}'")
                
                # Categoría/Competición (asumimos segunda celda)
                category = cells[1].text.strip()
                
                # Nombre del evento (tercera celda)
                event_cell = cells[2]
                
                # Extraer nombres de equipos
                event_name = extract_event_name(event_cell)
                print(f"      Evento: {event_name}")
                
                # Buscar canales Acestream en los detalles
                channels = find_acestream_channels(row)
                
                if channels:
                    print(f"      Canales encontrados: {len(channels)}")
                else:
                    print(f"      No se encontraron canales Acestream")
                
                # Solo agregar eventos con canales Acestream
                if channels:
                    # Limpiar y formatear el nombre del evento
                    event_name = clean_event_name(event_name)
                    
                    events.append({
                        'date': formatted_date,
                        'time': time_str,
                        'category': category,
                        'name': event_name,
                        'channels': channels
                    })
                    
            except Exception as e:
                print(f"    Error procesando fila {row_idx}: {str(e)}")
                continue
    
    return events

def parse_date(date_text):
    """
    Parsear fecha del texto a formato DD-MM
    
    Args:
        date_text: Texto con la fecha
        
    Returns:
        Fecha en formato "DD-MM"
    """
    try:
        # Patrones comunes
        patterns = [
            r'(\d{1,2})[/-](\d{1,2})',            # 18/10, 18-10
            r'(\d{1,2})\s+(\w{3})',               # 18 Oct
            r'\w{3}\s+(\d{1,2})\s+(\w{3})',       # Vie 18 Oct
            r'(\d{1,2})\s+de\s+(\w+)',            # 18 de Octubre
        ]
        
        for pattern in patterns:
            match = re.search(pattern, date_text, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    day = match.group(1).zfill(2)
                    
                    # Si el segundo grupo es numérico (mes)
                    if match.group(2).isdigit():
                        month = match.group(2).zfill(2)
                    else:
                        # Convertir nombre de mes a número
                        month_name = match.group(2).lower()[:3]
                        month_map = {
                            'ene': '01', 'feb': '02', 'mar': '03', 'abr': '04',
                            'may': '05', 'jun': '06', 'jul': '07', 'ago': '08',
                            'sep': '09', 'oct': '10', 'nov': '11', 'dic': '12',
                            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
                        }
                        month = month_map.get(month_name, datetime.now().strftime('%m'))
                    
                    return f"{day}-{month}"
        
        # Si no se puede parsear, usar fecha actual
        today = datetime.now()
        return today.strftime("%d-%m")
        
    except:
        today = datetime.now()
        return today.strftime("%d-%m")

def extract_event_name(event_cell):
    """
    Extraer nombre del evento desde la celda HTML
    
    Args:
        event_cell: Celda HTML con información del evento
        
    Returns:
        Nombre del evento
    """
    # Buscar equipos en la estructura del HTML (basado en tu HTML)
    teams = event_cell.find_all('div', {'class': 'team-container'})
    if len(teams) >= 2:
        team1_name = teams[0].find('div', {'class': 'team-name'})
        team2_name = teams[1].find('div', {'class': 'team-name'})
        
        team1 = team1_name.text.strip() if team1_name else "Equipo 1"
        team2 = team2_name.text.strip() if team2_name else "Equipo 2"
        
        return f"{team1} vs {team2}"
    
    # Buscar texto con "vs" o "-"
    text = event_cell.text.strip()
    if ' vs ' in text or ' VS ' in text or ' - ' in text:
        # Limpiar texto
        text = re.sub(r'\s+', ' ', text)
        return text
    
    # Buscar cualquier texto relevante
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if lines:
        return lines[0]
    
    return "Evento Deportivo"

def find_acestream_channels(event_row):
    """
    Buscar canales Acestream en los detalles del evento
    
    Args:
        event_row: Fila HTML del evento
        
    Returns:
        Lista de canales con IDs Acestream
    """
    channels = []
    
    # Buscar fila de detalles siguiente (basado en tu HTML)
    detail_row = event_row.find_next_sibling('tr', {'class': 'event-detail'})
    
    if not detail_row:
        # Buscar cualquier elemento hermano que contenga detalles
        next_elem = event_row.find_next_sibling()
        while next_elem and next_elem.name == 'tr':
            if 'event-detail' in str(next_elem.get('class', '')):
                detail_row = next_elem
                break
            next_elem = next_elem.find_next_sibling()
    
    if detail_row:
        # Buscar enlaces de streaming
        # En tu HTML, los enlaces están en <a class="stream-link">
        stream_links = detail_row.find_all('a', {'class': 'stream-link'})
        
        if not stream_links:
            # Buscar cualquier enlace que contenga acestream
            stream_links = detail_row.find_all('a', href=re.compile(r'acestream', re.IGNORECASE))
        
        if not stream_links:
            # Buscar cualquier enlace
            stream_links = detail_row.find_all('a', href=True)
        
        for link in stream_links:
            href = link.get('href', '')
            link_text = link.text.strip()
            
            # Buscar ID Acestream (40 caracteres hexadecimales)
            acestream_pattern = r'[a-fA-F0-9]{40}'
            matches = re.findall(acestream_pattern, href)
            
            if matches:
                acestream_id = matches[0]
                channel_name = link_text if link_text else f"Canal {len(channels)+1}"
                
                # También buscar en el texto del enlace
                if not channel_name or channel_name == f"Canal {len(channels)+1}":
                    # Verificar si el texto contiene nombre de canal
                    parent_text = link.parent.text if link.parent else ""
                    if 'DAZN' in parent_text:
                        channel_name = 'DAZN'
                    elif 'Movistar' in parent_text:
                        channel_name = 'Movistar'
                    elif 'Sport' in parent_text:
                        channel_name = 'Sport TV'
                
                channels.append({
                    'id': acestream_id,
                    'name': channel_name
                })
            else:
                # También buscar en el texto del enlace
                if 'acestream://' in href:
                    # Extraer ID después de acestream://
                    id_match = re.search(r'acestream://([a-fA-F0-9]+)', href)
                    if id_match and len(id_match.group(1)) == 40:
                        acestream_id = id_match.group(1)
                        channel_name = link_text if link_text else f"Canal {len(channels)+1}"
                        channels.append({
                            'id': acestream_id,
                            'name': channel_name
                        })
    
    return channels

def clean_event_name(event_name, max_length=80):
    """
    Limpiar y formatear el nombre del evento
    
    Args:
        event_name: Nombre del evento
        max_length: Longitud máxima
        
    Returns:
        Nombre limpio del evento
    """
    # Eliminar espacios extras
    event_name = re.sub(r'\s+', ' ', event_name).strip()
    
    # Eliminar caracteres problemáticos para M3U
    event_name = re.sub(r'[<>:"/\\|?*]', '', event_name)
    
    # Limitar longitud
    if len(event_name) > max_length:
        event_name = event_name[:max_length-3] + "..."
    
    return event_name

def generate_m3u_content(events):
    """
    Generar contenido M3U a partir de los eventos
    
    Args:
        events: Lista de eventos
        
    Returns:
        Contenido M3U como string
    """
    lines = []
    
    # Encabezado M3U (actualizado según tu ejemplo)
    lines.append('#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/refs/heads/master/guiatv.xml,https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz,https://raw.githubusercontent.com/davidmuma/EPG_dobleM/master/guiatv.xml" refresh="3600"')
    lines.append('#EXTVLCOPT:network-caching=1000')
    lines.append('')  # Línea en blanco
    
    if not events:
        lines.append('# No hay eventos disponibles')
        return '\n'.join(lines)
    
    # Ordenar eventos por fecha y hora
    def event_sort_key(event):
        try:
            # Parsear fecha DD-MM
            date_parts = event['date'].split('-')
            if len(date_parts) == 2:
                day = int(date_parts[0])
                month = int(date_parts[1])
            else:
                day = 1
                month = 1
            
            # Parsear hora HH:MM
            time_parts = event['time'].split(':')
            if len(time_parts) == 2:
                hour = int(time_parts[0])
                minute = int(time_parts[1])
            else:
                hour = 0
                minute = 0
            
            # Usar año actual
            year = datetime.now().year
            month = min(max(month, 1), 12)  # Asegurar mes válido
            day = min(max(day, 1), 31)      # Asegurar día válido
            
            return datetime(year, month, day, hour, minute)
        except:
            return datetime.now()
    
    events.sort(key=event_sort_key)
    
    # Generar entradas para cada evento-canal
    channel_count = 0
    for event in events:
        for channel in event['channels']:
            channel_count += 1
            
            # Formato: fecha + categoría
            group_title = f"{event['date']} {event['category']}"
            
            # Formato: hora + nombre evento + (primeros 3 chars del ID)
            # Basado en tu ejemplo: "Burgos - Valencia (N-911)"
            short_id = channel['id'][:3]
            channel_display_name = f"{event['time']} {event['name']} (N-{short_id})"
            
            # URL Acestream
            acestream_url = f"http://127.0.0.1:6878/ace/getstream?id={channel['id']}"
            
            # Línea EXTINF (basado en tu ejemplo)
            # Tu formato: #EXTINF:-1 tvg-id="M+ LaLiga 2 HD" tvg-name="Burgos - Valencia (N-911)" group-title="COPA DEL REY",Burgos - Valencia (N-911)
            
            # Extraer tvg-id del nombre del canal
            tvg_id = "Evento Deportivo"
            if 'DAZN' in channel['name']:
                tvg_id = "DAZN F1 HD"
            elif 'Movistar' in channel['name']:
                tvg_id = "Movistar Plus+ HD"
            elif 'M+' in channel['name'] or 'LaLiga' in channel['name']:
                tvg_id = "M+ LaLiga HD"
            elif 'Sport' in channel['name']:
                tvg_id = "Sport TV"
            
            lines.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{channel_display_name}" group-title="{group_title}",{channel_display_name}')
            lines.append(acestream_url)
    
    print(f"Canales generados en M3U: {channel_count}")
    return '\n'.join(lines)

def save_m3u_file(content, filename='zz_eventos_ott.m3u'):
    """
    Guardar contenido M3U en archivo
    
    Args:
        content: Contenido M3U
        filename: Nombre del archivo
        
    Returns:
        True si se guardó correctamente
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Archivo guardado: {filename}")
        return True
    except Exception as e:
        print(f"✗ Error guardando archivo: {str(e)}")
        return False

def manage_history(m3u_content, history_dir='history', max_history=50):
    """
    Gestionar histórico de archivos
    
    Args:
        m3u_content: Contenido M3U actual
        history_dir: Directorio de histórico
        max_history: Máximo número de archivos a mantener
        
    Returns:
        True si se guardó en histórico (contenido diferente)
    """
    try:
        # Crear directorio si no existe
        os.makedirs(history_dir, exist_ok=True)
        
        # Calcular hash del contenido actual
        current_hash = hashlib.md5(m3u_content.encode('utf-8')).hexdigest()
        
        # Buscar el último archivo en el histórico
        history_files = []
        if os.path.exists(history_dir):
            history_files = sorted([
                f for f in os.listdir(history_dir) 
                if f.endswith('.m3u') and f.startswith('zz_eventos_')
            ])
        
        # Verificar si el contenido es diferente al último
        save_to_history = True
        
        if history_files:
            last_file = os.path.join(history_dir, history_files[-1])
            try:
                with open(last_file, 'r', encoding='utf-8') as f:
                    last_content = f.read()
                last_hash = hashlib.md5(last_content.encode('utf-8')).hexdigest()
                
                if current_hash == last_hash:
                    print("ℹ️ El contenido no ha cambiado, no se guardará en el histórico")
                    save_to_history = False
                else:
                    print("✓ Contenido diferente al anterior")
            except:
                print("⚠️ No se pudo leer el archivo histórico anterior")
        
        # Guardar en histórico si es diferente
        if save_to_history:
            # Generar nombre con timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            history_file = os.path.join(history_dir, f'zz_eventos_ott_{timestamp}.m3u')
            
            with open(history_file, 'w', encoding='utf-8') as f:
                f.write(m3u_content)
            print(f"✓ Archivo guardado en histórico: {history_file}")
            
            # Mantener solo los últimos archivos
            if len(history_files) >= max_history:
                files_to_delete = history_files[:-(max_history-1)]  # Eliminar los más antiguos
                for file in files_to_delete:
                    try:
                        os.remove(os.path.join(history_dir, file))
                        print(f"  Eliminado archivo antiguo: {file}")
                    except:
                        pass
        
        return save_to_history
        
    except Exception as e:
        print(f"✗ Error gestionando histórico: {str(e)}")
        return False

def main():
    """
    Función principal
    """
    print("=== Scraping de Eventos Deportivos desde IPFS ===")
    print(f"Iniciando: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Configuración
    ipns_hash = "k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004"
    path = "?tab=agendaDeportiva"  # CORREGIDO: Usar el nombre correcto de la pestaña
    
    print(f"IPNS Hash: {ipns_hash}")
    print(f"Path: {path}")
    
    # Obtener contenido HTML
    print(f"\nObteniendo contenido desde IPNS...")
    html_content = get_ipfs_content(ipns_hash, path)
    
    if not html_content:
        print("✗ No se pudo obtener el contenido")
        return False
    
    print(f"✓ Contenido obtenido ({len(html_content)} caracteres)")
    
    # Guardar HTML completo para debug
    debug_html = 'ipfs_content.html'
    with open(debug_html, 'w', encoding='utf-8') as f:
        f.write(html_content[:100000])  # Primeros 100k caracteres
    print(f"✓ HTML guardado para debug: {debug_html}")
    
    # Extraer eventos
    print("\nExtrayendo eventos...")
    events = extract_events_from_html(html_content)
    
    print(f"\n=== RESULTADOS ===")
    print(f"Eventos encontrados: {len(events)}")
    
    total_channels = sum(len(e['channels']) for e in events)
    print(f"Canales Acestream totales: {total_channels}")
    
    # Mostrar resumen por fecha
    if events:
        dates_summary = {}
        for event in events:
            date = event['date']
            if date not in dates_summary:
                dates_summary[date] = 0
            dates_summary[date] += len(event['channels'])
        
        print("\nCanales por fecha:")
        for date, count in sorted(dates_summary.items()):
            print(f"  {date}: {count} canales")
    
    # Generar contenido M3U
    m3u_content = generate_m3u_content(events)
    
    # Guardar archivo principal
    print(f"\nGenerando archivo M3U...")
    if save_m3u_file(m3u_content):
        print(f"✓ Archivo principal creado: zz_eventos_ott.m3u")
        print(f"  Líneas totales: {m3u_content.count(chr(10)) + 1}")
        
        # Contar canales reales
        channel_lines = m3u_content.count('getstream?id=')
        print(f"  Canales Acestream: {channel_lines}")
        
        # Gestionar histórico
        print(f"\nGestionando histórico...")
        manage_history(m3u_content)
        
        # Guardar debug info
        if events:
            debug_file = 'events_debug.json'
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump(events, f, indent=2, ensure_ascii=False, default=str)
            print(f"✓ Archivo de depuración: {debug_file}")
        
        return True
    else:
        print("✗ Error generando archivo M3U")
        return False

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
