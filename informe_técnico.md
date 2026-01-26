# Documentación Técnica: Sistema de Actualización Ezdakit

**Versión:** 2.1  
**Última Actualización:** Enero 2026  
**Script Principal:** `.github/scripts/update_system.py`  
**Workflow:** `.github/workflows/update_all.yml`

---

## 1. Visión General
Este sistema automatiza la generación de listas de reproducción IPTV (`.m3u`) mediante la fusión de fuentes externas, limpieza de nombres, filtrado por lista negra y generación de una agenda de eventos deportivos basada en scraping web.

El proceso se ejecuta automáticamente en **GitHub Actions** cada hora (Cron `0 * * * *`).

---

## 2. Fuentes de Datos (Inputs)

### A. Listas IPTV Externas (Descarga Dinámica)
El sistema descarga dos listas base a través de gateways IPFS públicos. Se utiliza redundancia (varias URLs) por si falla una pasarela.

| Fuente | Código Interno | Identificador IPNS | Prioridad de Datos |
| :--- | :--- | :--- | :--- |
| **New Era** | `N` | `k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004` | **Alta** (Sus nombres/grupos prevalecen) |
| **Elcano** | `E` | `k51qzi5uqu5di462t7j4vu4akwfhvtjhy88qbupktvoacqfqe9uforjvhyi4wr` | **Baja** (Rellena huecos) |

> **Nota:** La llave única para cruzar ambas listas es el **`acestream_id`** (Hash de 40 caracteres).

### B. Agenda Deportiva (Web Scraping)
* **URL Base:** `https://ipfs.io/ipns/k2k4r8oqlcjxsritt5mczkcn4mmvcmymbqw7113fz2flkrerfwfps004/?tab=agenda`
* **Formato:** HTML.
* **Datos extraídos:** Fecha, Hora, Competición, Evento y **Dial/Canal** (ej: "M54").

### C. Archivos de Control Local (Carpeta `canales/`)
Archivos CSV estáticos que definen las reglas de negocio.

1.  **`listado_canales.csv`** (La Piedra Rosetta)
    * Relaciona el dial que aparece en la web con el ID interno de la guía.
    * **Columnas:** `Canal`, `Dial_Movistar(M)`, `Dial_Orange(O)`, `TV_guide_id`.
    * *Uso:* Si la web dice "M54", este CSV nos dice que eso equivale al `tvg-id="M+ LaLiga HD"`.

2.  **`lista_negra.csv`** (Censura/Corrección)
    * **Columnas:** `ace_id`, `canal_real`.
    * *Uso:* Si un ID está aquí, se marca como blacklist. Si tiene `canal_real`, se usa ese nombre en el sufijo.

---

## 3. Lógica del Proceso: Fase 1 (Canales)
Generación del archivo maestro `ezdakit.m3u`.

1.  **Fusión (Merge):**
    * Se unen las listas `E` y `N`.
    * Si un ID existe en ambas, se quedan los metadatos de **New Era**.
    
2.  **Limpieza de Nombres (`clean_channel_name`):**
    * Se eliminan calidades (`FHD`, `1080p`, `4K`), códecs (`HEVC`), etiquetas de idioma (`(ES)`) y sufijos basura (`|`, `vip`).
    * **Regla Especial:** Se elimina la palabra **"BAR"** completa mediante Regex `\bBAR\b`.
    * El resultado se guarda como **`nombre_supuesto`**.

3.  **Aplicación de Blacklist:**
    * Si el ID está en `lista_negra.csv`:
        * Grupo -> `ZZ_Canales_KO`.
        * Nombre -> Se añade sufijo ` >>> BLACKLIST` o ` >>> [Nombre Real CSV]`.

4.  **Ordenación:**
    * Criterio estricto: 1º por **Grupo (A-Z)**, 2º por **Nombre Supuesto (A-Z)**.

---

## 4. Lógica del Proceso: Fase 2 (Eventos)
Generación de `ezdakit_eventos.m3u` mediante triangulación de datos.

### El Flujo de Triangulación
Para que un evento aparezca, deben alinearse 3 elementos:



1.  **Extracción Web:**
    * Se lee el HTML y se busca el texto del canal (ej: "M+ LaLiga (M54)").
    * Regex extrae el número del dial: **`54`**.
    
2.  **Mapeo (Cruce con `listado_canales.csv`):**
    * El script busca `54` en la columna `Dial_Movistar(M)`.
    * Recupera el **`TV_guide_id`** (ej: "M+ LaLiga HD") y el **`Canal`** (nombre oficial).

3.  **Búsqueda de Emisión (Cruce con Base de Datos Maestra):**
    * El script busca en la lista de canales procesada en la Fase 1 todos los canales que tengan `tvg-id="M+ LaLiga HD"`.
    * Si hay 3 canales con ese ID (ej: uno HD, uno FHD, uno SD), se generan **3 eventos**.

### Formato de Salida
El nombre del canal en la lista de eventos se construye así:
`Hora-Evento (Nombre Oficial CSV) (Calidad) (PrefixID)`

*Ejemplo:*
`21:00-Real Madrid vs Barcelona (M+ LALIGA) (FHD) (a4f)`

---

## 5. Archivos Generados (Outputs)

| Archivo | Descripción | Ordenación |
| :--- | :--- | :--- |
| **`ezdakit.m3u`** | Lista final jugable. Incluye canales limpios y blacklist al final. | Grupo -> Nombre |
| **`correspondencias.csv`** | Auditoría. Muestra ID, nombres originales, nombre limpio y estado blacklist. | Grupo -> Nombre |
| **`ezdakit_eventos.m3u`** | Lista temporal de eventos deportivos del día. | Fecha -> Hora |
| **`eventos_canales.csv`** | Histórico/Log de eventos detectados y sus coincidencias. | Fecha -> Hora |
| **`.debug/agenda_dump.html`** | Copia del HTML descargado de la agenda (para depuración). | N/A |

---

## 6. Automatización (GitHub Actions)

El archivo `.github/workflows/update_all.yml` controla la ejecución.

* **Frecuencia:** Cada hora (`0 * * * *`).
* **Modo Testing:**
    * Se puede lanzar manualmente activando el check "Activar Modo Testing".
    * Esto añade el argumento `--testing` al script Python.
    * **Consecuencia:** El script busca archivos de entrada acabados en `_testing.csv` y genera salidas acabadas en `_testing.m3u`.

### Variables de Entorno
Para solucionar problemas de ejecución en Cron, se usa la variable intermedia:
`IS_TESTING: ${{ inputs.testing_mode || 'false' }}`
Esto evita fallos cuando el input es nulo (ejecución automática).

---

## 7. Guía Rápida de Mantenimiento

* **¿Canales mal nombrados?** -> Revisa la función `clean_channel_name` en `update_system.py`.
* **¿Falta un evento?**
    1.  Mira el Dial en la web (HTML en `.debug/`).
    2.  Mira si ese Dial existe en `canales/listado_canales.csv`.
    3.  Mira si el `TV_guide_id` de ese dial tiene canales asociados en `correspondencias.csv`.
* **¿Quitar un canal?** -> Añade su ID a `canales/lista_negra.csv`.
