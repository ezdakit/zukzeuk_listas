const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Obtener los parámetros
const zeronetAddress = process.argv[2];
const outputFolder = process.argv[3];
const outputFile = process.argv[4];

if (!zeronetAddress || !outputFolder || !outputFile) {
  console.error('Error: Faltan parámetros. Uso: node extract-events.js <zeronet-address> <output-folder> <output-file>');
  process.exit(1);
}

const folderPath = path.join(__dirname, '..', outputFolder);
const filePath = path.join(folderPath, outputFile);

console.log('Parámetros recibidos:');
console.log(`- Dirección ZeroNet: ${zeronetAddress}`);
console.log(`- Carpeta de destino: ${folderPath}`);
console.log(`- Archivo de salida: ${filePath}`);

(async () => {
  console.log('Iniciando el script...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  try {
    const zeronetUrl = `http://127.0.0.1:43110/${zeronetAddress}/`;
    console.log(`Extrayendo contenido de: ${zeronetUrl}`);

    // Configuración con tiempos de espera extendidos
    await page.goto(zeronetUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 120000 // 2 minutos para cargar la página
    });

    console.log('Página principal cargada, esperando iframe...');

    // Esperar a que el iframe esté cargado
    await page.waitForSelector('#inner-iframe', { timeout: 30000 });
    console.log('Iframe encontrado');

    // Obtener el frame del iframe
    const frameHandle = await page.$('#inner-iframe');
    const frame = await frameHandle.contentFrame();
    
    // Esperar a que el contenido del iframe esté listo
    console.log('Esperando contenido dentro del iframe...');
    await frame.waitForLoadState('networkidle', { timeout: 60000 });

    // Tomar captura de pantalla del iframe para diagnóstico
    await frame.screenshot({ path: path.join(folderPath, 'debug-iframe.png') });
    console.log('Captura del iframe guardada');

    // Esperar la tabla de eventos dentro del iframe
    try {
      await frame.waitForSelector('#events-table', { timeout: 30000 });
      console.log('Tabla de eventos encontrada en el iframe');

      // Extraer el HTML completo del iframe
      const iframeContent = await frame.content();
      
      // Crear la carpeta si no existe
      if (!fs.existsSync(folderPath)) {
        fs.mkdirSync(folderPath, { recursive: true });
      }

      // Guardar el contenido
      fs.writeFileSync(filePath, iframeContent);
      console.log(`Contenido del iframe guardado en: ${filePath}`);

    } catch (error) {
      console.error('No se pudo encontrar la tabla en el iframe:', error);
      
      // Guardar el contenido del iframe de todos modos para diagnóstico
      const fallbackContent = await frame.content();
      fs.writeFileSync(filePath, fallbackContent);
      console.log('Se guardó contenido de fallback del iframe');

      // Mostrar estructura del iframe para diagnóstico
      const iframeStructure = await frame.evaluate(() => {
        const ids = Array.from(document.querySelectorAll('[id]')).map(el => el.id);
        const classes = Array.from(document.querySelectorAll('[class]')).flatMap(el => el.className.split(' '));
        return { ids, classes };
      });
      console.log('Estructura del iframe:', JSON.stringify(iframeStructure, null, 2));
    }

  } catch (error) {
    console.error('Error durante la extracción:', error);
    
    // Guardar el contenido de la página principal para diagnóstico
    const mainContent = await page.content();
    if (!fs.existsSync(folderPath)) {
      fs.mkdirSync(folderPath, { recursive: true });
    }
    fs.writeFileSync(filePath, mainContent);
    console.log('Se guardó contenido de la página principal para diagnóstico');
    
  } finally {
    await browser.close();
    console.log('Navegador cerrado');
  }
})();
