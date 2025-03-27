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

(async () => {
  if (!(await isZeroNetRunning())) {
    console.error('Error: ZeroNet no está funcionando. Saliendo...');
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  const zeronetUrl1 = `http://127.0.0.1:43110/${zeronetAddress1}/`;
  console.log(`Extrayendo contenido de: ${zeronetUrl1}`);

  try {
    // Configurar timeouts
    await page.setDefaultNavigationTimeout(120000);
    await page.setDefaultTimeout(60000);

    // Navegar a la página
    console.log('Navegando a la página...');
    await page.goto(zeronetUrl1, { 
      waitUntil: 'networkidle',
      timeout: 120000
    });

    // Esperar a que el iframe se cargue - versión alternativa sin eval
    console.log('Esperando iframe...');
    await page.waitForSelector('#inner-iframe', { 
      state: 'attached',
      timeout: 60000 
    });

    // Verificar visibilidad del iframe de forma segura
    const isIframeVisible = await page.$eval('#inner-iframe', iframe => {
      return iframe.offsetWidth > 0 && iframe.offsetHeight > 0;
    });
    
    if (!isIframeVisible) {
      throw new Error('El iframe no es visible');
    }

    // Obtener el iframe
    const iframeHandle = await page.$('#inner-iframe');
    const frame = await iframeHandle.contentFrame();

    // Esperar contenido dinámico dentro del iframe
    console.log('Esperando tabla de eventos...');
    await frame.waitForSelector('#events-table', {
      state: 'visible',
      timeout: 60000
    });

    // Esperar un poco más para contenido dinámico
    await page.waitForTimeout(5000);

    // Obtener HTML final del iframe
    console.log('Obteniendo contenido final...');
    const finalContent = await frame.content();

    // Guardar archivo
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
