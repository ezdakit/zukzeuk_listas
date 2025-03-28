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

// Función para verificar si ZeroNet está funcionando
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

// Función para generar nombre de archivo secuencial
function getSequentialFilename(basePath, baseName, extension, index) {
  const paddedIndex = index.toString().padStart(3, '0');
  return path.join(basePath, `${baseName}_${paddedIndex}${extension}`);
}

(async () => {
  if (!(await isZeroNetRunning())) {
    console.error('Error: ZeroNet no está funcionando. Saliendo...');
    process.exit(1);
  }

  const browser = await chromium.launch();
  const page = await browser.newPage();
  const zeronetUrl1 = `http://127.0.0.1:43110/${zeronetAddress1}/`;

  try {
    await page.setExtraHTTPHeaders({ 'Accept': 'text/html' });
    await page.goto(zeronetUrl1, { waitUntil: 'load', timeout: 60000 });

    console.log('Esperando a que el iframe se cargue...');
    await page.waitForSelector('#inner-iframe', { timeout: 20000 });
    const iframeHandle = await page.$('#inner-iframe');
    const frame = await iframeHandle.contentFrame();

    // Crear la carpeta si no existe
    const folderPath = path.join(__dirname, '..', outputFolder);
    if (!fs.existsSync(folderPath)) {
      fs.mkdirSync(folderPath, { recursive: true });
    }

    // Extraer la información de la extensión del archivo de salida
    const ext = path.extname(outputFile);
    const baseName = path.basename(outputFile, ext);

    console.log('Iniciando captura de contenido cada 5 segundos...');
    const duration = 60; // 60 segundos total
    const interval = 5;  // cada 5 segundos
    const iterations = duration / interval;

    for (let i = 0; i < iterations; i++) {
      try {
        const currentTime = new Date().toISOString().replace(/[:.]/g, '-');
        const sequentialFile = getSequentialFilename(folderPath, baseName, ext, i);
        
        console.log(`[${i+1}/${iterations}] Obteniendo contenido...`);
        
        // Verificar si el iframe sigue disponible
        const isIframeAlive = await page.$('#inner-iframe').catch(() => false);
        if (!isIframeAlive) {
          console.error('El iframe ha desaparecido. Deteniendo la captura.');
          break;
        }

        // Obtener contenido del iframe
        const content = await frame.content();
        
        // Añadir marca de tiempo al contenido
        const timestampedContent = `<!-- Captura ${i+1} - ${currentTime} -->\n${content}`;
        
        fs.writeFileSync(sequentialFile, timestampedContent);
        console.log(`Contenido guardado en: ${sequentialFile}`);

        // Esperar para la próxima captura (excepto en la última iteración)
        if (i < iterations - 1) {
          await new Promise(resolve => setTimeout(resolve, interval * 1000));
        }
      } catch (error) {
        console.error(`Error en la iteración ${i+1}:`, error.message);
      }
    }

    console.log('Captura completada. Archivos guardados en:', folderPath);
  } catch (error) {
    console.error('Error durante el proceso:', error.message);
  } finally {
    await browser.close();
  }
})();
