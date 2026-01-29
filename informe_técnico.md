Especificación Técnica: Sistema de Procesamiento de IPTV y Agenda Deportiva
1. Arquitectura de Archivos y Entradas de Datos
El sistema opera sobre una estructura de carpetas específica y requiere tres tipos de archivos CSV de configuración manual.

A. Entradas Locales (Carpeta /canales)
1. lista_negra.csv (Filtro de Exclusión)
Propósito: Identificar transmisiones (IDs) que deben ser ignoradas en la generación de listas finales.

Lectura: Se carga en un diccionario hash: {'acestream_id': 'canal_real'}.

Uso: Si un ID procesado existe en este diccionario, se marca internamente como in_blacklist = "yes".

2. canales_forzados.csv (Sobreescritura Manual)
Propósito: Definir metadatos inmutables para IDs específicos, anulando cualquier información proveniente de la web o listas M3U.

Lectura: Se carga en un diccionario anidado clave-valor.

Estructura de Datos:

Python
{
  'acestream_id': {
     'tvg': 'Valor de columna tvg-id',
     'name': 'Valor de columna nombre_supuesto',
     'group': 'Valor de columna grupo',
     'quality': 'Valor de columna calidad'
  }
}
Codificación: Se maneja explícitamente la eliminación del BOM (\ufeff) si existe.

3. listado_canales.csv (Mapeo de Diales)
Propósito: Traductor de "Número de Dial Físico" a "Identificador Lógico de Canal".

Lectura: Diccionario donde la clave es el número de dial.

Estructura:

Python
{
  'Número_Dial (ej: 52)': {
     'tvg': 'TV_guide_id (ej: M+ LaLiga)',
     'name': 'Canal (Nombre legible)'
  }
}
2. Algoritmos de Procesamiento de Canales (ETL)
El núcleo del sistema fusiona múltiples fuentes (listas M3U) en una única "Base de Datos Maestra" (master_db).

Paso 2.1: Descarga y Parsing de M3U
Fuentes: "Elcano" y "New Era" (múltiples espejos/mirrors para redundancia).

Lógica de Extracción (Regex):

ID: Se busca en la URL el patrón de 40 caracteres hexadecimales: ([0-9a-fA-F]{40}).

Metadatos: De la línea #EXTINF se extraen:

tvg-id="..."

group-title="..."

Nombre: Texto después de la última coma.

Paso 2.2: Algoritmo de Limpieza de Nombres (clean_channel_name)
Esta función transforma el nombre "sucio" de la lista M3U en el nombre_supuesto.

Eliminación de Basura: Se elimina todo texto después de la cadena -->.

Lista de Términos Prohibidos (Case Insensitive): Se eliminan mediante reemplazo vacío las siguientes cadenas:

Resoluciones/Codecs: 1080p, 720p, FHD, UHD, 4K, 8K, HD, SD, 50fps, HEVC, AAC, H.265.

Etiquetas: (ES), (SP), (RU), (Mxx), (Oxx), (BACKUP), |, vip, premium, ( original ).

Tratamiento de BAR: Se usa el regex \bBAR\b. Esto significa que solo elimina la palabra "BAR" si es una palabra completa. Elimina "M+ LaLiga BAR" pero NO elimina "BARCELONA" ni "BARÇA".

Limpieza de Espacios: Se colapsan espacios dobles y se eliminan guiones o guiones bajos al final.

Eliminación de Sufijo de ID: Si el nombre termina con los últimos 4 caracteres del ID de Acestream, se eliminan esos 4 caracteres.

Eliminación de Hexadecimales: Se elimina cualquier bloque de 4 caracteres hexadecimales al final del nombre (\s+[0-9a-fA-F]{4}$).

Paso 2.3: Fusión y Construcción de la Master DB
Se itera sobre el conjunto único (set) de todos los IDs encontrados. Para cada ID:

Prioridad de Datos:

Se intenta obtener datos (Nombre, Grupo, TVG) de la lista "New Era".

Si no existen, se usan los de "Elcano".

Recuperación Cruzada de TVG: Si un canal viene de Elcano sin tvg-id, el sistema busca si el nombre de ese canal existe en la lista New Era. Si hay coincidencia de nombre, se "roba" el tvg-id de New Era y se le asigna al ID de Elcano.

Generación de nombre_supuesto: Se aplica la función clean_channel_name explicada en 2.2.

Detección de Calidad: Se busca en el nombre original (antes de limpiar) para asignar etiquetas: (UHD) si contiene 4K/UHD, (FHD) si contiene 1080/FHD, (HD) por defecto.

Aplicación de canales_forzados (Override):

El sistema verifica si el ID actual existe en el diccionario de forzados.

SI EXISTE: Se descartan todos los datos calculados anteriormente.

Se asigna directamente: nombre_supuesto = forzado['name'], final_group = forzado['group'], final_tvg = forzado['tvg'].

La calidad se toma del CSV forzado y se convierte a mayúsculas.

Verificación de Lista Negra: Se consulta el diccionario de lista_negra. Si está, in_blacklist = "yes".

Salidas Generadas en esta fase:
correspondencias.csv: Volcado crudo de la master_db con columnas: ID, nombres originales, TVGs, nombre supuesto, grupo final, calidad, estado de blacklist.

ezdakit.m3u: Lista general.

Si in_blacklist == "yes", el grupo se fuerza a ZZ_Canales_KO y se añade el nombre real al final del nombre visible.

3. Algoritmos de Procesamiento de Agenda (Scraping)
El script descarga el HTML de la agenda deportiva y ejecuta la lógica de detección de diales.

Paso 3.1: Parsing HTML
Se buscan bloques div con clase events-day para obtener la fecha (data-date).

Se itera cada fila tr con clase event-row.

Se extrae: Hora, Competición (div competition-info) y Evento (atributo data-event-id o tercera celda td).

Paso 3.2: Extracción y Limpieza de Dial
Por cada canal listado en la web (span channel-link), se obtiene el texto visible (ej: "M+ LaLiga (M52)") y se aplica la siguiente lógica estricta para encontrar el número:

Intento 1 (Patrón Movistar): Regex \([^)]*?M(\d+)[^)]*?\). Busca una 'M' seguida de dígitos dentro de paréntesis.

Captura: (M52) -> 52. (M+52) -> 52.

Intento 2 (Patrón Numérico Genérico): Regex \((\d+)\). Busca solo dígitos entre paréntesis.

Condición de Exclusión: Este intento se aborta si el texto del canal contiene la palabra "ORANGE" (en mayúsculas/minúsculas). Esto evita confundir diales de Orange con los de Movistar.

Captura: (52) -> 52.

Si no se extrae ningún número, el canal se marca como Descartado (motivo: unlisted).

Paso 3.3: Vinculación (Dial -> TVG -> IDs)
Una vez obtenido el número de dial (ej: "52"):

Consulta al Mapa: Se busca "52" en el diccionario cargado de listado_canales.csv.

Si no existe: Descartado (motivo: unlisted).

Si existe: Se recupera el target_tvg (ej: "M+ LaLiga").

Búsqueda Inversa en Master DB:

El sistema recorre toda la master_db.

Selecciona todos los IDs donde item['final_tvg'] == target_tvg.

Nota: Esto permite una relación "Uno a Muchos". Un solo evento de agenda puede generar 5 líneas en el M3U final si existen 5 enlaces diferentes para ese canal (distintas calidades, backups, etc.).

Filtrado de Vacíos: Si el dial existe pero no hay ningún canal en la base de datos con ese TVG, se marca como Descartado (motivo: no_streams).

Salidas Generadas en esta fase:
eventos_canales.csv: Registro detallado de cada stream encontrado para cada evento.

descartes.csv: Registro de fallos (diales no encontrados, canales sin streams, etc.).

ezdakit_eventos.m3u: Lista final de reproducción.

Agrupación: #EXTINF:-1 group-title="MES-DÍA COMPETICIÓN" ...

Nombre Visible: HORA-EVENTO (NOMBRE_CANAL_CSV)(CALIDAD) (PREFIJO_ID)

URL: Enlace local HTTP al motor Acestream (http://127.0.0.1:6878/ace/getstream?id=...).

4. Resumen de Flujo de Datos
Entrada: Listas M3U Raw + CSVs Configuración.

Proceso 1: Limpieza de nombres (eliminación de "BAR", res, etc.) y fusión inteligente.

Proceso 2 (Override): canales_forzados.csv aplasta cualquier dato calculado.

Almacenamiento: Se guarda todo en memoria (master_db) indexado por TVG-ID.

Entrada: Agenda Web.

Proceso 3: Extracción de dial numérico (Regex).

Cruce: Dial Numérico -> listado_canales.csv -> TVG-ID -> master_db -> IDs de Acestream.

Salida: Listas M3U formateadas.
