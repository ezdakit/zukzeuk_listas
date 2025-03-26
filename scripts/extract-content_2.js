const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Obtener parámetros
const [,, zeronetAddress, outputFolder, outputFile] = process.argv;

if (!zeronetAddress || !outputFolder || !outputFile) {
  console.error('Uso: node script.js <zeronet-address> <output-folder> <output-file>');
  process.exit(1);
}

const folderPath = path.join(__dirname, '..', outputFolder);
const filePath = path.join(folderPath, outputFile);

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    console.log(`Accediendo a: http://127.0.0.1:43110/${zeronetAddress}/`);
    await page.goto(`http://127.0.0.1:43110/${zeronetAddress}/`, {
      waitUntil: 'networkidle',
      timeout: 120000
    });

    // Esperar y acceder al iframe específico
    console.log('Localizando iframe...');
    const frameHandle = await page.waitForSelector('#inner-iframe', { timeout: 30000 });
    const frame = await frameHandle.contentFrame();

    // Esperar componentes específicos de la tabla de eventos
    console.log('Esperando carga de la tabla...');
    await frame.waitForSelector('.table-container', { timeout: 30000 });
    await frame.waitForSelector('#events-table', { timeout: 30000 });
    await frame.waitForSelector('.status.pronto', { timeout: 30000 });

    // Extraer HTML completo de la sección de la tabla
    console.log('Extrayendo contenido...');
    const tableHtml = await frame.$eval('.table-container', el => el.outerHTML);

    // Guardar archivo
    if (!fs.existsSync(folderPath)) {
      fs.mkdirSync(folderPath, { recursive: true });
    }
    fs.writeFileSync(filePath, tableHtml);
    console.log(`Tabla guardada en: ${filePath}`);

    // Verificación final
    if (tableHtml.includes('events-table')) {
      console.log('Extracción completada con éxito');
    } else {
      console.warn('Advertencia: El contenido puede estar incompleto');
    }

  } catch (error) {
    console.error('Error durante la extracción:', error);
    
    // Guardar diagnóstico
    const diagnostics = {
      error: error.toString(),
      timestamp: new Date().toISOString(),
      pageContent: await page?.content?.(),
      iframeContent: await frame?.content?.(),
      screenshots: {
        main: await page.screenshot({ encoding: 'base64' }),
        iframe: await frame?.screenshot?.({ encoding: 'base64' })
      }
    };

    fs.writeFileSync(
      path.join(folderPath, 'diagnostics.json'),
      JSON.stringify(diagnostics, null, 2)
    );
    
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
