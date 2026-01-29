Informe Técnico Actualizado (v1.8).

Este documento refleja la arquitectura actual del sistema tras la implementación de la limpieza estricta de nombres y el cambio de paradigma en la vinculación (Matching por Nombre en lugar de por Dial).

Informe Técnico: Sistema Automatizado de Gestión de Canales IPTV y Agenda Deportiva (v1.8)
1. Resumen del Sistema
El sistema es un flujo de trabajo ejecutado por el script update_system.py con dos objetivos:

Fusión y Normalización: Generar una "Master DB" de canales limpia a partir de listas M3U externas.

Generación de Agenda: Scraping de una web deportiva para generar una lista M3U de eventos en vivo.

Cambio Crítico v1.7+: La vinculación entre la web y los canales internos ya no se basa en el número de dial, sino en el Nombre del Canal Normalizado. El número de dial se utiliza únicamente como filtro de admisión (si no tiene dial, se ignora).

2. Entradas del Sistema (Inputs)
2.1. Archivos Locales (canales/)
listado_canales.csv (Base de Conocimiento):

Función: Actúa como diccionario de traducción.

Carga Dual: El script carga este archivo en dos diccionarios en memoria:

dial_map: Índice por número (para validaciones).

name_map: Índice por Nombre del Canal en Mayúsculas (para la vinculación).

Columnas: Dial_Movistar(M), TV_guide_id, Canal.

lista_negra.csv:

Función: Filtro de exclusión por ID.

Lógica: Si un ID está presente, se marca con in_blacklist='yes'.

canales_forzados.csv:

Función: Override (sobreescritura) de metadatos.

Prioridad: Máxima. Ignora datos de M3U externas.

2.2. Fuentes Remotas
Listas M3U (Elcano/New Era): Fuentes raw de canales.

Agenda HTML: Web alojada en IPFS (con sistema de rotación de proxies "Smart Fetch" para evitar datos obsoletos).

3. Algoritmos de Procesamiento (ETL)
Fase 1: Ingesta y Normalización de Canales (Master DB)
Descarga y Parsing: Se extraen IDs, nombres y grupos de las listas externas.

Limpieza de Nombres (clean_channel_name):

Eliminación de sufijos técnicos (1080p, HEVC, etc.).

Eliminación de cadenas específicas ("BAR" como palabra completa, "(ES)", etc.).

Conversión: Se fuerza todo el nombre a MAYÚSCULAS.

Fusión: Se priorizan datos de "New Era" sobre "Elcano". Se inyectan datos de canales_forzados.csv si existen.

Resultado: Una lista de objetos en memoria (master_db) indexada por TVG-ID.

Fase 2: Scraping y Normalización de Agenda (El Núcleo v1.8)
Se descarga el HTML y se iteran los eventos. Para cada canal detectado en la web (texto raw), se sigue este estricto proceso:

Paso 2.1: Captura de Datos Crudos
Se lee el texto original del elemento HTML.

Almacenamiento: Se guarda tal cual en la variable canal_agenda_real (para auditoría en CSV).

Ejemplo: "M+ LaLiga TV (M52)"

Paso 2.2: Detección de Dial (Filtro de Admisión)
Se busca un patrón de dial (M52) o (52) usando Regex.

Regla de Negocio: Si NO se detecta un dial, el evento se descarta inmediatamente (motivo: no_dial_detected).

Nota: Aunque detectamos el número, ya no lo usamos para buscar el canal, solo para saber que es un evento válido de TV.

Paso 2.3: Limpieza y Normalización (canal_agenda)
Se toma el texto original y se aplican transformaciones secuenciales estrictas usando Expresiones Regulares (Regex):

Eliminación del Dial: Se borra el texto (M52) o (52).

Mayúsculas: .upper().

Reglas de Reemplazo (Orden Específico):

ELLAS VAMOS -> MOVISTAR ELLAS

M+ DEPORTES -> MOVISTAR DEPORTES

LALIGA TV HYPERMOTION -> HYPERMOTION

DAZN LALIGA -> DAZN LA LIGA (solo el texto, no afecta números posteriores).

Eliminación de : VER PARTIDO (con tolerancia a espacios).

PLUS+ -> PLUS

Eliminación del prefijo M+ al inicio del nombre.

LALIGA -> M+ LALIGA (Re-inserción de prefijo para estandarizar).

Regla de Exactitud Final:

Si el resultado es exactamente DAZN LA LIGA, se convierte a DAZN LA LIGA 1. (Evita romper DAZN LA LIGA 2).

Resultado: Variable canal_agenda.

Ejemplo: M+ LALIGA TV

Paso 2.4: Vinculación (Matching)
Búsqueda: Se busca el valor de canal_agenda en la columna Canal del archivo listado_canales.csv (usando el índice name_map).

Resolución:

Si hay coincidencia -> Se obtiene el TVG-ID.

Si no hay coincidencia -> Se descarta (motivo: mapping_not_found_for: ...).

Obtención de Streams: Con el TVG-ID obtenido, se buscan todos los enlaces Acestream correspondientes en la master_db.

4. Salidas del Sistema (Outputs)
4.1. canales/eventos_canales.csv (Auditoría Completa)
Archivo CSV que registra cada enlace generado. Estructura de columnas crítica:

acestream_id

dial_M: El número detectado (solo informativo).

tvg_id: El ID interno usado para el cruce.

fecha, hora, evento, competición.

nombre_canal: El nombre oficial según listado_canales.csv.

canal_agenda: El nombre procesado y normalizado (usado para el cruce).

canal_agenda_real: El texto crudo original de la web (para debug).

calidad, lista_negra.

4.2. ezdakit_eventos.m3u (Producto Final)
Lista de reproducción para el usuario final.

Nombre Visible: HORA-EVENTO (NOMBRE_OFICIAL) (CALIDAD) (ID_CORTO)

Agrupación: Por día y competición.

4.3. canales/correspondencias.csv
Volcado de la base de datos de canales disponibles.

Detalle: La columna nombre_supuesto contiene siempre nombres en MAYÚSCULAS.

4.4. canales/descartes.csv
Log de errores.

Registra eventos que tenían dial pero cuyo canal_agenda normalizado no coincidió con ninguna entrada en listado_canales.csv.

5. Resumen Lógico para Reproducción (Prompting)
Si necesitas regenerar este sistema, esta es la lógica nuclear:

"El sistema debe cargar listado_canales.csv creando un mapa Nombre -> TVG_ID. Al procesar la agenda web:

Extraer texto crudo (canal_agenda_real).

Verificar si existe patrón de dial (Mxx) o (xx). Si no, descartar.

Eliminar el dial del texto y aplicar pipeline de normalización Regex (Mayúsculas, reemplazos específicos de Movistar/DAZN) para obtener canal_agenda.

Buscar canal_agenda en el mapa de nombres para obtener el TVG_ID.

Usar TVG_ID para recuperar streams de la base de datos de canales."

6. Control de Versiones
Versión Actual del Script: 1.8

Cambios Recientes:

v1.8: Inclusión de campo canal_agenda_real.

v1.7: Cambio de lógica de Matching (Dial -> Nombre).

v1.4-v1.6: Refinamiento de reglas Regex de normalización.
