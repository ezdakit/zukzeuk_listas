// capture_zeronet.js
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// --- Configuration ---
const ZERONET_BASE_URL = 'http://127.0.0.1:43110';
const OUTPUT_DIR = 'testing'; // El directorio donde se guardarán los ficheros
const SNAPSHOT_COUNT = 10; // Siempre tomaremos 10 muestras
const IFRAME_SELECTOR = '#inner-iframe'; // Default ZeroNet iframe ID

// --- Helper Functions ---
function printUsage() {
    console.error(`
Uso: node capture_zeronet.js <zeroNetSiteId> <baseFilename> <waitTimeMultiplier>

Argumentos:
  <zeroNetSiteId>      : El Site ID de ZeroNet (ej: 1HeLLo4uzjaLetFx6NH3PMwFP3qbRbTf3D)
  <baseFilename>       : El nombre base para los ficheros HTML de salida (ej: captura_sitio)
  <waitTimeMultiplier> : Un entero. El tiempo total de espera será multiplier * 10 segundos.
                         Las capturas se tomarán cada 'multiplier' segundos.

Ejemplo:
  node capture_zeronet.js 1HeLLo4uzjaLetFx6NH3PMwFP3qbRbTf3D mipagina 3
  (Esperará 30 segundos en total, tomando 10 capturas cada 3 segundos)
`);
}

/**
 * Borra los ficheros .html existentes en el directorio especificado.
 * @param {string} dirPath Ruta al directorio.
 */
async function cleanupOutputDir(dirPath) {
    try {
        if (fs.existsSync(dirPath)) {
            const files = fs.readdirSync(dirPath);
            console.log(`Limpiando ficheros .html existentes en '${dirPath}'...`);
            let deletedCount = 0;
            for (const file of files) {
                if (file.endsWith('.html')) {
                    const filePath = path.join(dirPath, file);
                    try {
                        fs.unlinkSync(filePath);
                        // console.log(`  Borrado: ${file}`); // Descomentar para más detalle
                        deletedCount++;
                    } catch (unlinkErr) {
                        console.error(`  Error borrando fichero ${filePath}:`, unlinkErr.message);
                    }
                }
            }
             if (deletedCount > 0) {
                 console.log(`  Se borraron ${deletedCount} fichero(s) .html.`);
             } else {
                 console.log(`  No se encontraron ficheros .html para borrar.`);
             }
        } else {
            console.log(`El directorio de salida '${dirPath}' no existe. Se creará.`);
        }
    } catch (err) {
        console.error(`Error durante la limpieza del directorio ${dirPath}:`, err.message);
        // Considerar si salir o continuar si falla la limpieza
        // process.exit(1);
    }
}

/**
 * Crea el directorio de salida si no existe.
 * @param {string} dirPath Ruta al directorio.
 */
async function createOutputDir(dirPath) {
    try {
        if (!fs.existsSync(dirPath)) {
            fs.mkdirSync(dirPath, { recursive: true });
            console.log(`Directorio de salida creado: '${dirPath}'`);
        } else {
             console.log(`El directorio de salida '${dirPath}' ya existe.`);
        }
    } catch (err) {
        console.error(`Error creando el directorio de salida '${dirPath}':`, err.message);
        process.exit(1); // Salir si no podemos crear el directorio
    }
}


// --- Main Script Logic ---
(async () => {
    // 1. Parsear Argumentos de Línea de Comandos
    const args = process.argv.slice(2); // Omitir 'node' y el nombre del script
    if (args.length !== 3) {
        console.error("Error: Número incorrecto de argumentos.");
        printUsage();
        process.exit(1);
    }

    const zeroNetSiteId = args[0];
    const baseFilename = args[1];
    const waitTimeMultiplier = parseInt(args[2], 10);

    if (isNaN(waitTimeMultiplier) || waitTimeMultiplier <= 0) {
        console.error("Error: <waitTimeMultiplier> debe ser un entero positivo.");
        printUsage();
        process.exit(1);
    }

    const totalWaitSeconds = waitTimeMultiplier * 10;
    const snapshotIntervalSeconds = waitTimeMultiplier; // (totalWaitSeconds / SNAPSHOT_COUNT) es simplemente waitTimeMultiplier
    const snapshotIntervalMs = snapshotIntervalSeconds * 1000;

    console.log(`--- Script de Captura de Página ZeroNet ---`);
    console.log(`Site ID          : ${zeroNetSiteId}`);
    console.log(`Nombre Base      : ${baseFilename}`);
    console.log(`Multiplicador    : ${waitTimeMultiplier}`);
    console.log(`Tiempo Total     : ${totalWaitSeconds} segundos`);
    console.log(`Intervalo Captura: ${snapshotIntervalSeconds} segundos (${SNAPSHOT_COUNT} capturas)`);
    console.log(`Directorio Salida: ${OUTPUT_DIR}`);
    console.log(`-----------------------------------------`);


    // 2. Preparar Directorio de Salida
    const outputDirPath = path.resolve(OUTPUT_DIR); // Obtener ruta absoluta
    await cleanupOutputDir(outputDirPath); // Borrar .html existentes
    await createOutputDir(outputDirPath);  // Asegurar que existe


    // 3. Lanzar Navegador y Navegar
    let browser;
    try {
        console.log("Lanzando navegador...");
        browser = await chromium.launch(); // Puedes cambiar a firefox o webkit si lo prefieres
        const context = await browser.newContext({
            // Ignorar errores HTTPS si ZeroNet usa certificados autofirmados (menos común ahora)
             ignoreHTTPSErrors: true,
        });
        const page = await context.newPage();

        const initialUrl = `${ZERONET_BASE_URL}/${zeroNetSiteId}/`;
        console.log(`Navegando a la página wrapper de ZeroNet: ${initialUrl}`);
        // Aumentar timeout si es necesario para arranque lento de ZeroNet/proxy
        await page.goto(initialUrl, { waitUntil: 'domcontentloaded', timeout: 90000 }); // 90 segundos timeout para carga inicial
        console.log("Página wrapper cargada (DOM content). Esperando por el iframe...");

        // Esperar específicamente a que el elemento iframe esté presente en el DOM
        try {
            await page.waitForSelector(IFRAME_SELECTOR, { timeout: 60000 }); // Esperar hasta 60s por la etiqueta iframe
            console.log("Elemento iframe encontrado.");
        } catch (error) {
             console.error(`Error: No se pudo encontrar el iframe ('${IFRAME_SELECTOR}') en 60 segundos.`);
             console.error("Comprueba si el sitio ZeroNet está cargando correctamente o si el ID del iframe ha cambiado.");
             await browser.close();
             process.exit(1);
        }

        // --- OBTENER EL FRAME CORRECTAMENTE ---
        // Primero, obtener el ElementHandle del iframe
        console.log("Obteniendo el manejador (handle) del elemento iframe...");
        const iframeElement = await page.$(IFRAME_SELECTOR);
        if (!iframeElement) {
            console.error(`Error: No se pudo obtener el ElementHandle para el iframe ('${IFRAME_SELECTOR}').`);
            await browser.close();
            process.exit(1);
        }

        // Segundo, obtener el objeto Frame real desde el ElementHandle
        console.log("Obteniendo el objeto Frame desde el manejador del elemento...");
        const frame = await iframeElement.contentFrame(); // <<< ESTO DEVUELVE EL OBJETO Frame
        if (!frame) {
            // Esto puede ocurrir si la etiqueta iframe existe pero su contenido (documento) no se cargó
            console.error(`Error: No se pudo obtener el objeto Frame del contenido del iframe. El frame podría no haberse cargado correctamente o estar restringido.`);
            // Podrías añadir una espera extra aquí si sospechas una condición de carrera
            // await page.waitForTimeout(5000);
            // const frame = await iframeElement.contentFrame(); // Intentar de nuevo
            // if (!frame) { /* salir si sigue sin encontrarse */ }
            await browser.close();
            process.exit(1);
        }
        console.log("Objeto Frame obtenido con éxito.");
        // --- FIN DE LA CORRECCIÓN ---

        // Puede tomar un momento para que el *contenido* del iframe comience a cargarse,
        // añadimos una pequeña espera inicial antes de la primera captura.
        console.log("Esperando brevemente a que el contenido del iframe comience a cargarse...");
        await page.waitForTimeout(3000); // 3 segundos de margen inicial


        // 4. Capturar Snapshots Periódicamente
        console.log(`Iniciando captura de snapshots cada ${snapshotIntervalSeconds} segundos...`);
        for (let i = 0; i < SNAPSHOT_COUNT; i++) {
            const startTime = Date.now();
            try {
                 // Obtener el contenido HTML *dentro* del iframe usando el objeto Frame
                const iframeContent = await frame.content(); // <<< USAR frame.content() AHORA FUNCIONA
                const filename = `${baseFilename}_${i}.html`;
                const filePath = path.join(outputDirPath, filename);

                fs.writeFileSync(filePath, iframeContent);
                const duration = Date.now() - startTime;
                console.log(`[${new Date().toLocaleTimeString()}] Guardada captura: ${filename} (obtenida en ${duration}ms)`);

                // Esperar para el siguiente intervalo, a menos que sea la última captura
                if (i < SNAPSHOT_COUNT - 1) {
                    await page.waitForTimeout(snapshotIntervalMs);
                }
            } catch (error) {
                const duration = Date.now() - startTime;
                 // Comprobar errores comunes cuando el frame deja de existir (navegación, cierre)
                 if (error.message.includes('frame was detached') || error.message.includes('Target closed') || error.message.includes('Protocol error') ) {
                    console.warn(`[${new Date().toLocaleTimeString()}] Aviso: El frame podría haberse cerrado o navegado durante la captura ${i}. Saltando. (Error: ${error.message})`);
                 } else {
                    console.error(`[${new Date().toLocaleTimeString()}] Error capturando o guardando snapshot ${i} (después de ${duration}ms):`, error.message);
                 }
                 // Opcional: Decidir si continuar o parar en caso de error
                 // break;
                 // Si se continúa, esperar igualmente el intervalo para mantener la temporización
                 if (i < SNAPSHOT_COUNT - 1) {
                    await page.waitForTimeout(snapshotIntervalMs);
                }
            }
        }

        console.log("Captura de snapshots finalizada.");

    } catch (error) {
        console.error("\nOcurrió un error durante el proceso:", error);
        process.exitCode = 1; // Indicar fallo
    } finally {
        if (browser) {
            console.log("Cerrando navegador...");
            await browser.close();
        }
        console.log("Script finalizado.");
    }
})(); // Fin de la función async auto-ejecutada
