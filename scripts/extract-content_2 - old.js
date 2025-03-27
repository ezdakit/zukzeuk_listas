const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Configuración
const DEBUG_MODE = true;
const MAX_RETRIES = 3;
const TIMEOUT = 120000;

// Obtener parámetros
const [,, zeronetAddress, outputFolder, outputFile] = process.argv;

if (!zeronetAddress || !outputFolder || !outputFile) {
  console.error('Uso: node script.js <zeronet-address> <output-folder> <output-file>');
  process.exit(1);
}

const folderPath = path.join(__dirname, '..', outputFolder);
const filePath = path.join(folderPath, outputFile);

// Función para guardar diagnóstico
async function saveDebugData(error, page, frame) {
  try {
    console.log('Preparando datos de diagnóstico...');
    
    const debugData = {
      timestamp: new Date().toISOString(),
      error: error?.toString() || 'Unknown error',
      stack: error?.stack,
      params: { zeronetAddress, outputFolder, outputFile },
      page: {
        url: page?.url(),
        content: await safeGetContent(page),
        screenshot: await safeGetScreenshot(page)
      },
      frame: {
        url: await safeGetFrameUrl(frame),
        content: await safeGetContent(frame),
        screenshot: await safeGetScreenshot(frame)
      }
    };

    const debugPath = path.join(folderPath, 'debug');
    if (!fs.existsSync(debugPath)) {
      fs.mkdirSync(debugPath, { recursive: true });
    }

    fs.writeFileSync(
      path.join(debugPath, `debug_${Date.now()}.json`),
      JSON.stringify(debugData, null, 2)
    );

    console.log('Datos de diagnóstico guardados');
  } catch (debugError) {
    console.error('Error al guardar diagnóstico:', debugError);
  }
}

// Funciones seguras para obtener datos
async function safeGetContent(context) {
  try {
    return await context?.content?.() || null;
  } catch {
    return null;
  }
}

async function safeGetScreenshot(context) {
  try {
    if (!context) return null;
    const screenshotPath = path.join(folderPath, 'debug', `screenshot_${Date.now()}.png`);
    await context.screenshot({ path: screenshotPath });
    return screenshotPath;
  } catch {
    return null;
  }
}

async function safeGetFrameUrl(frame) {
  try {
    return await frame?.evaluate?.('location.href') || null;
  } catch {
    return null;
  }
}

// Función principal
(async () => {
  console.log('=== INICIO DEL SCRIPT ===');
  console.log('Parámetros:');
  console.log(`- ZeroNet Address: ${zeronetAddress}`);
  console.log(`- Output Folder: ${folderPath}`);
  console.log(`- Output File: ${filePath}`);

  let browser;
  let page;
  let frame;
  let attempt = 0;
  let success = false;

  try {
    // Preparar carpeta de salida
    if (!fs.existsSync(folderPath)) {
      fs.mkdirSync(folderPath, { recursive: true });
    }

    // Iniciar navegador
    console.log('\nIniciando navegador...');
    browser = await chromium.launch({ 
      headless: true,
      timeout: TIMEOUT
    });
    page = await browser.newPage();

    // Intentar varias veces
    while (attempt < MAX_RETRIES && !success) {
      attempt++;
      console.log(`\n=== INTENTO ${attempt} de ${MAX_RETRIES} ===`);

      try {
        // Navegar a la URL
        const url = `http://127.0.0.1:43110/${zeronetAddress}/`;
        console.log(`Navegando a: ${url}`);
        await page.goto(url, {
          waitUntil: 'domcontentloaded',
          timeout: TIMEOUT
        });

        // Esperar iframe
        console.log('Buscando iframe...');
        const frameHandle = await page.waitForSelector('#inner-iframe', { 
          timeout: TIMEOUT/2 
        });
        frame = await frameHandle.contentFrame();
        console.log('Iframe encontrado');

        // Esperar contenido dentro del iframe
        console.log('Esperando contenido del iframe...');
        await frame.waitForLoadState('networkidle', { timeout: TIMEOUT });
        console.log('Contenido del iframe cargado');

        // Verificar componentes clave
        console.log('Verificando elementos de la tabla...');
        await frame.waitForSelector('.table-container', { timeout: TIMEOUT/3 });
        await frame.waitForSelector('#events-table', { timeout: TIMEOUT/3 });
        console.log('Elementos clave encontrados');

        // Extraer contenido
        console.log('Extrayendo HTML de la tabla...');
        const tableHtml = await frame.$eval('.table-container', el => el.outerHTML);
        
        // Guardar archivo
        fs.writeFileSync(filePath, tableHtml);
        console.log(`\n✅ ÉXITO: Tabla guardada en ${filePath}`);
        success = true;

      } catch (attemptError) {
        console.error(`❌ Error en intento ${attempt}:`, attemptError.message);
        
        // Guardar datos de diagnóstico
        if (DEBUG_MODE) {
          await saveDebugData(attemptError, page, frame);
        }

        // Esperar antes de reintentar
        if (attempt < MAX_RETRIES) {
          const waitTime = 5000 * attempt;
          console.log(`Esperando ${waitTime/1000} segundos antes de reintentar...`);
          await new Promise(resolve => setTimeout(resolve, waitTime));
        }
      }
    }

    if (!success) {
      throw new Error(`No se pudo completar la extracción después de ${MAX_RETRIES} intentos`);
    }

  } catch (finalError) {
    console.error('\n❌ ERROR CRÍTICO:', finalError.message);
    
    // Guardar diagnóstico final
    if (DEBUG_MODE) {
      await saveDebugData(finalError, page, frame);
    }

    // Guardar contenido disponible como fallback
    try {
      const fallbackContent = await safeGetContent(page) || await safeGetContent(frame) || '<h1>No se pudo obtener contenido</h1>';
      fs.writeFileSync(filePath, fallbackContent);
      console.log(`Se guardó contenido de fallback en ${filePath}`);
    } catch (fileError) {
      console.error('Error al guardar fallback:', fileError);
    }

    process.exit(1);
  } finally {
    // Cerrar navegador
    if (browser) {
      console.log('\nCerrando navegador...');
      await browser.close().catch(e => console.error('Error al cerrar navegador:', e));
    }
    console.log('=== FIN DEL SCRIPT ===');
  }
})();
