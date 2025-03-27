const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Obtener los parámetros
const zeronetAddress1 = process.argv[2];
const outputFolder = process.argv[3];
const outputFile = process.argv[4];

if (!zeronetAddress1 || !outputFolder || !outputFile) {
  console.error('Error: Faltan parámetros. Uso: node extract-content.js <zeronet-address-1> <output-folder> <output-file>');
  process.exit(1);
}

const folderPath = path.join(__dirname, '..', outputFolder);
const filePath = path.join(folderPath, outputFile);

console.log('Parámetros recibidos:');
console.log(`- Dirección 1: ${zeronetAddress1}`);
console.log(`- Carpeta de destino: ${folderPath}`);
console.log(`- Archivo de salida: ${filePath}`);

async function isZeroNetRunning() {
  console.log('Verificando si ZeroNet está funcionando...');
  try {
    const response = await fetch('http://127.0.0.1:43110', {
      headers: { 'Accept': 'text/html' },
    });
    return response.ok;
  } catch (error) {
    console.error('Error al verificar ZeroNet:', error.message);
    return false;
  }
}

async function waitForContent(page, selector, timeout = 30000) {
  console.log(`Esperando selector: ${selector}`);
  try {
    await page.waitForSelector(selector, { state: 'attached', timeout });
    await page.waitForSelector(selector, { state: 'visible', timeout });
    return true;
  } catch (error) {
    console.error(`Error esperando selector ${selector}:`, error.message);
    return false;
  }
}

(async () => {
  if (!(await isZeroNetRunning())) {
    console.error('Error: ZeroNet no está funcionando. Saliendo...');
    process.exit(1);
  }

  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  
  const zeronetUrl1 = `http://127.0.0.1:43110/${zeronetAddress1}/`;
  console.log(`Extrayendo contenido de: ${zeronetUrl1}`);

  try {
    // Configurar timeout más largo para la navegación
    await page.setDefaultNavigationTimeout(120000); // 2 minutos
    await page.setDefaultTimeout(60000); // 1 minuto para otros timeouts

    // Configurar encabezados
    await page.setExtraHTTPHeaders({
      'Accept': 'text/html',
    });

    // Navegar a la página
    console.log('Navegando a la página...');
    await page.goto(zeronetUrl1, { 
      waitUntil: 'domcontentloaded',
      timeout: 120000
    });

    // Esperar a que la página termine de cargar completamente
    console.log('Esperando a que la página termine de cargar...');
    await page.waitForFunction(() => {
      return document.readyState === 'complete';
    }, { timeout: 120000 });

    // Esperar a que el iframe se cargue y sea visible
    const iframeLoaded = await waitForContent(page, '#inner-iframe');
    if (!iframeLoaded) {
      throw new Error('No se pudo cargar el iframe');
    }

    // Obtener el iframe
    const iframeHandle = await page.$('#inner-iframe');
    const frame = await iframeHandle.contentFrame();

    // Esperar a que el contenido dinámico dentro del iframe esté listo
    console.log('Esperando contenido dinámico dentro del iframe...');
    await frame.waitForSelector('#events-table', { state: 'visible', timeout: 60000 });
    
    // Esperar un poco más para asegurar que el contenido está completamente renderizado
    await frame.waitForTimeout(3000);

    // Obtener el HTML final
    console.log('Obteniendo el HTML final...');
    const finalContent = await frame.content();

    // Guardar el archivo
    if (!fs.existsSync(folderPath)) {
      fs.mkdirSync(folderPath, { recursive: true });
    }
    fs.writeFileSync(filePath, finalContent);
    console.log(`Contenido guardado en: ${filePath}`);

  } catch (error) {
    console.error('Error durante la extracción:', error);
    process.exit(1);
  } finally {
    await browser.close();
    console.log('Navegador cerrado.');
  }
})();
