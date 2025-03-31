// capture_zeronet.js
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// --- Configuration ---
const ZERONET_BASE_URL = 'http://127.0.0.1:43110';
const OUTPUT_DIR = 'testing';
const SNAPSHOT_COUNT = 10;
const IFRAME_SELECTOR = '#inner-iframe';

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
                        deletedCount++;
                    } catch (unlinkErr) {
                        console.error(`  Error borrando fichero ${filePath}:`, unlinkErr.message);
                    }
                }
            }
             if (deletedCount > 0) console.log(`  Se borraron ${deletedCount} fichero(s) .html.`);
             else console.log(`  No se encontraron ficheros .html para borrar.`);
        } else {
            console.log(`El directorio de salida '${dirPath}' no existe. Se creará.`);
        }
    } catch (err) {
        console.error(`Error durante la limpieza del directorio ${dirPath}:`, err.message);
    }
}

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
        process.exit(1);
    }
}

// --- Main Script Logic ---
(async () => {
    const args = process.argv.slice(2);
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
    const snapshotIntervalSeconds = waitTimeMultiplier;
    const snapshotIntervalMs = snapshotIntervalSeconds * 1000;

    console.log(`--- Script de Captura de Página ZeroNet ---`);
    console.log(`Site ID          : ${zeroNetSiteId}`);
    console.log(`Nombre Base      : ${baseFilename}`);
    console.log(`Multiplicador    : ${waitTimeMultiplier}`);
    console.log(`Tiempo Total     : ${totalWaitSeconds} segundos`);
    console.log(`Intervalo Captura: ${snapshotIntervalSeconds} segundos (${SNAPSHOT_COUNT} capturas)`);
    console.log(`Directorio Salida: ${OUTPUT_DIR}`);
    console.log(`-----------------------------------------`);

    const outputDirPath = path.resolve(OUTPUT_DIR);
    await cleanupOutputDir(outputDirPath);
    await createOutputDir(outputDirPath);

    let browser;
    try {
        console.log("Lanzando navegador...");
        browser = await chromium.launch();
        const context = await browser.newContext({ ignoreHTTPSErrors: true });
        const page = await context.newPage();

        // <<< CAPTURE CONSOLE LOGS >>>
        page.on('console', msg => console.log(`BROWSER CONSOLE (Page): ${msg.type().toUpperCase()} - ${msg.text()}`));

        const initialUrl = `${ZERONET_BASE_URL}/${zeroNetSiteId}/`;
        console.log(`Navegando a la página wrapper de ZeroNet: ${initialUrl}`);
        await page.goto(initialUrl, { waitUntil: 'domcontentloaded', timeout: 90000 });
        console.log("Página wrapper cargada (DOM content). Esperando por el iframe...");

        try {
            await page.waitForSelector(IFRAME_SELECTOR, { timeout: 60000 });
            console.log("Elemento iframe encontrado.");
        } catch (error) {
             console.error(`Error: No se pudo encontrar el iframe ('${IFRAME_SELECTOR}') en 60 segundos.`);
             await browser.close();
             process.exit(1);
        }

        console.log("Obteniendo el manejador (handle) del elemento iframe...");
        const iframeElement = await page.$(IFRAME_SELECTOR);
        if (!iframeElement) {
            console.error(`Error: No se pudo obtener el ElementHandle para el iframe ('${IFRAME_SELECTOR}').`);
            await browser.close();
            process.exit(1);
        }

        console.log("Obteniendo el objeto Frame desde el manejador del elemento...");
        const frame = await iframeElement.contentFrame();
        if (!frame) {
            console.error(`Error: No se pudo obtener el objeto Frame del contenido del iframe. El frame podría no haberse cargado correctamente.`);
            await browser.close();
            process.exit(1);
        }
        console.log("Objeto Frame obtenido con éxito.");
        console.log("DEBUG: Frame URL:", frame.url()); // Log URL being loaded by frame


        // <<< WAIT FOR ACTUAL CONTENT INSIDE IFRAME >>>
        console.log("Esperando que aparezca contenido dentro del iframe (body > *)...");
        try {
            // Wait for the body element within the frame to exist AND have at least one child element
            await frame.waitForSelector('body > *', { timeout: 60000 }); // Wait up to 60s
            console.log("Contenido inicial detectado dentro del iframe.");
        } catch (e) {
            console.warn("Advertencia: Timeout esperando contenido específico (body > *) dentro del iframe después de 60s.");
            console.warn("El sitio puede estar vacío, cargar muy lento o usar una estructura inesperada.");
            console.log("URL actual del frame:", frame.url());
            // Consider continuing or exiting based on your needs
            // If you continue, the first snapshot(s) might still be empty.
        }
        // <<< END OF WAIT FOR CONTENT >>>


        // 4. Capture Snapshots Periodically
        console.log(`Iniciando captura de snapshots cada ${snapshotIntervalSeconds} segundos...`);
        for (let i = 0; i < SNAPSHOT_COUNT; i++) {
            const startTime = Date.now();
            try {
                const iframeContent = await frame.content();
                const filename = `${baseFilename}_${i}.html`;
                const filePath = path.join(outputDirPath, filename);
                fs.writeFileSync(filePath, iframeContent);
                const duration = Date.now() - startTime;
                console.log(`[${new Date().toLocaleTimeString()}] Guardada captura: ${filename} (obtenida en ${duration}ms)`);

                if (i < SNAPSHOT_COUNT - 1) {
                    await page.waitForTimeout(snapshotIntervalMs);
                }
            } catch (error) {
                const duration = Date.now() - startTime;
                 if (error.message.includes('frame was detached') || error.message.includes('Target closed') || error.message.includes('Protocol error') ) {
                    console.warn(`[${new Date().toLocaleTimeString()}] Aviso: El frame podría haberse cerrado o navegado durante la captura ${i}. Saltando. (Error: ${error.message})`);
                 } else {
                    console.error(`[${new Date().toLocaleTimeString()}] Error capturando o guardando snapshot ${i} (después de ${duration}ms):`, error.message);
                 }
                 if (i < SNAPSHOT_COUNT - 1) {
                    await page.waitForTimeout(snapshotIntervalMs);
                }
            }
        }
        console.log("Captura de snapshots finalizada.");

    } catch (error) {
        console.error("\nOcurrió un error durante el proceso:", error);
        process.exitCode = 1;
    } finally {
        if (browser) {
            console.log("Cerrando navegador...");
            await browser.close();
        }
        console.log("Script finalizado.");
    }
})();
