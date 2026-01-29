# Informe Técnico: Sistema Automatizado de Gestión de Canales IPTV y Agenda Deportiva (v1.8)

## 1. Resumen del Sistema

El sistema es un flujo de trabajo (*workflow*) ejecutado mediante un script de Python (`update_system.py`) que cumple dos objetivos principales:

1.  **Fusión y Normalización:** Descargar múltiples listas M3U de fuentes externas, limpiarlas, fusionarlas y enriquecerlas con metadatos locales para generar una "Master DB" (Lista Maestra) limpia.
2.  **Generación de Agenda:** Realizar *scraping* de una web externa de eventos deportivos, detectar transmisiones y generar una lista de reproducción (M3U) específica con los eventos en vivo.

> **Cambio Crítico (v1.7+):** La vinculación entre la web y los canales internos **ya no se basa en el número de dial**, sino en el **Nombre del Canal Normalizado**. El número de dial se utiliza únicamente como *filtro de admisión* (si el evento no tiene dial, se ignora).

---

## 2. Entradas del Sistema (Inputs)

### 2.1. Archivos Locales de Configuración (`canales/`)
Estos archivos actúan como la "verdad absoluta" y prevalecen sobre los datos remotos.

* **`listado_canales.csv` (Base de Conocimiento)**
    * **Función:** Diccionario maestro de traducción y vinculación.
    * **Carga Dual:** El script carga este archivo en dos índices en memoria:
        1.  `dial_map`: Índice por número (para validaciones de existencia).
        2.  `name_map`: Índice por **Nombre del Canal en Mayúsculas** (para el *matching*).
    * **Columnas:** `Dial_Movistar(M)`, `TV_guide_id`, `Canal`.

* **`lista_negra.csv`**
    * **Función:** Filtro de exclusión por ID de Acestream.
    * **Lógica:** Si un ID aparece aquí, se marca internamente como `in_blacklist='yes'` y se excluye de la lista limpia final.

* **`canales_forzados.csv`**
    * **Función:** *Override* (sobreescritura) manual de metadatos.
    * **Prioridad:** Máxima. Si un ID está aquí, se ignoran los datos provenientes de las listas M3U web.

### 2.2. Fuentes Remotas
* **Listas M3U (Elcano y New Era):** Listas crudas alojadas en IPFS. Se definen múltiples *mirrors* para redundancia.
* **Agenda HTML:** Web alojada en IPFS que contiene la programación deportiva. Se utiliza un sistema de **"Smart Fetch"** que rota entre varios *gateways* hasta encontrar uno con fecha actual.

---

## 3. Algoritmos de Procesamiento (ETL)

El script `update_system.py` ejecuta las siguientes fases secuenciales:

### Fase 1: Ingesta y Normalización de Canales (Master DB)
1.  **Descarga y Parsing:** Se procesan las listas externas extrayendo ID, Nombre y Grupo.
2.  **Limpieza de Nombres (`clean_channel_name`):**
    * Eliminación de sufijos técnicos (`1080p`, `HEVC`, `[M...]`, etc.).
    * Eliminación de palabras clave como `(ES)` o `BAR` (solo si es palabra completa).
    * **Conversión:** Se fuerza el nombre final a **MAYÚSCULAS**.
3.  **Fusión:** Se crea un conjunto único de IDs. En caso de conflicto, los datos de "New Era" tienen prioridad sobre "Elcano".
4.  **Resultado:** Una lista de objetos en memoria (`master_db`) indexada por `TVG-ID`.

### Fase 2: Scraping y Normalización de Agenda (El Núcleo v1.8)
Se descarga el HTML de la agenda y se iteran los eventos. Para cada canal detectado en el texto de la web, se sigue este proceso estricto:

#### Paso 2.1: Captura de Datos Crudos
* Se lee el texto original del elemento HTML.
* **Almacenamiento:** Se guarda tal cual en la variable `canal_agenda_real` (para auditoría y detección de errores futuros).
    * *Ejemplo:* `"M+ LaLiga TV (M52)"`

#### Paso 2.2: Detección de Dial (Filtro de Admisión)
* Se busca un patrón de dial `(M52)` o `(52)` mediante Expresiones Regulares (Regex).
* **Regla de Negocio:** Si **NO** se detecta un dial, el evento se descarta inmediatamente (`motivo: no_dial_detected`).
* *Nota:* El número detectado ya no se usa para buscar el canal, solo valida que es un evento televisado relevante.

#### Paso 2.3: Limpieza y Normalización (`canal_agenda`)
Se toma el texto original y se aplican transformaciones secuenciales estrictas para generar una clave de búsqueda válida:

1.  **Eliminación del Dial:** Se borra el texto `(M52)` o `(52)`.
2.  **Mayúsculas:** Se aplica `.upper()`.
3.  **Reglas de Reemplazo (Orden Específico con Regex):**
    * `ELLAS VAMOS` &rarr; `MOVISTAR ELLAS`
    * `M+ DEPORTES` &rarr; `MOVISTAR DEPORTES`
    * `LALIGA TV HYPERMOTION` &rarr; `HYPERMOTION`
    * `DAZN LALIGA` &rarr; `DAZN LA LIGA` (Reemplazo parcial).
    * Eliminación de `: VER PARTIDO` (tolerante a espacios extra).
    * `PLUS+` &rarr; `PLUS`
    * Eliminación del prefijo `M+ ` al inicio del nombre.
    * `LALIGA` &rarr; `M+ LALIGA` (Reinserción de prefijo para estandarizar).
4.  **Regla de Exactitud Final:**
    * Si el resultado es **exactamente** `DAZN LA LIGA`, se convierte a `DAZN LA LIGA 1`. (Esto evita romper canales como `DAZN LA LIGA 2`).

* **Resultado:** Variable `canal_agenda`.
    * *Ejemplo Final:* `M+ LALIGA TV`

#### Paso 2.4: Vinculación (Matching)
1.  **Búsqueda:** Se busca el valor de `canal_agenda` en la columna `Canal` del archivo `listado_canales.csv` (usando el índice `name_map`).
2.  **Resolución:**
    * **Si hay coincidencia:** Se obtiene el `TVG-ID`.
    * **Si no hay coincidencia:** Se descarta el evento (`motivo: mapping_not_found_for: ...`).
3.  **Obtención de Streams:** Con el `TVG-ID`, se recuperan todos los enlaces Acestream activos de la `master_db`.

---

## 4. Salidas del Sistema (Outputs)

### 4.1. `canales/eventos_canales.csv` (Auditoría)
Archivo CSV detallado que registra cada enlace generado. Columnas clave:
* `dial_M`: El número detectado (informativo).
* `nombre_canal`: El nombre oficial en el CSV local.
* **`canal_agenda`**: El nombre procesado y normalizado (usado para el cruce).
* **`canal_agenda_real`**: El texto crudo original de la web (para debug).
* `tvg_id`: El ID interno.

### 4.2. `ezdakit_eventos.m3u` (Producto Final)
Lista de reproducción dinámica para el usuario final.
* **Formato del nombre:** `HORA-EVENTO (NOMBRE_OFICIAL) (CALIDAD) (ID_CORTO)`
* **Agrupación:** `#EXTINF:-1 group-title="FECHA COMPETICIÓN" ...`

### 4.3. `canales/descartes.csv`
Log de errores y eventos ignorados. Fundamental para ajustar las reglas de normalización si la web cambia los nombres.

---

## 5. Resumen Lógico para Reproducción (Prompting)

Si fuera necesario regenerar el código desde cero, esta es la directriz lógica nuclear:

> "El sistema debe cargar `listado_canales.csv` creando un mapa `Nombre -> TVG_ID`.
> Al procesar la agenda web:
> 1. Extraer texto crudo (`canal_agenda_real`).
> 2. Verificar si existe patrón de dial `(Mxx)` o `(xx)`. Si no, descartar.
> 3. Eliminar el dial del texto y aplicar pipeline de normalización Regex (Mayúsculas, reemplazos específicos de Movistar/DAZN) para obtener `canal_agenda`.
> 4. Buscar `canal_agenda` en el mapa de nombres para obtener el `TVG_ID`.
> 5. Usar `TVG_ID` para recuperar streams de la base de datos de canales."

---

## 6. Historial de Versiones (Changelog)

* **v1.8:** Inclusión del campo `canal_agenda_real` en CSV para auditoría de textos crudos.
* **v1.7:** Cambio de paradigma de *Matching*: de Dial a Nombre.
* **v1.6:** Regla de exactitud para "DAZN LA LIGA 1".
* **v1.5:** Regla de normalización "LALIGA" -> "M+ LALIGA".
* **v1.4:** Implementación de limpieza robusta basada en Regex.
