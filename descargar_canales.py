import sqlite3
import Levenshtein

# Conexión a la base datos SQLite
conn = sqlite3.connect('zz_canales.db')
cursor = conn.cursor()

# Obtener todos los registros de canales_iptv_temp
cursor.execute("SELECT id, name_original FROM canales_iptv_temp")
canales_iptv_temp = cursor.fetchall()

# Procesar cada registro de canales_iptv_temp
for canal in canales_iptv_temp:
    id_temp, name_original = canal
    
    # Buscar registros en correspondencia_canales donde channel_root sea una subcadena de name_original
    cursor.execute("SELECT id, channel_root, iptv_epg_id_new, iptv_group_new, name_new FROM correspondencia_canales WHERE ? LIKE '%' || channel_root || '%'", (name_original,))
    posibles_correspondencias = cursor.fetchall()
    
    if posibles_correspondencias:
        # Si hay más de una correspondencia, elegir la que tenga la menor distancia de Levenshtein
        mejor_correspondencia = min(posibles_correspondencias, key=lambda x: Levenshtein.distance(name_original, x[1]))
        
        # Actualizar el registro en canales_iptv_temp con los datos de la mejor correspondencia
        cursor.execute("""
            UPDATE canales_iptv_temp
            SET activo = 1,
                iptv_epg_id_new = ?,
                iptv_group_new = ?,
                name_new = ?
            WHERE id = ?
        """, (mejor_correspondencia[2], mejor_correspondencia[3], mejor_correspondencia[4], id_temp))
    else:
        # Si no se encuentra ninguna correspondencia, marcar el campo activo a 0
        cursor.execute("UPDATE canales_iptv_temp SET activo = 0 WHERE id = ?", (id_temp,))

# Guardar los cambios y cerrar la conexión a la base de datos
conn.commit()
conn.close()
