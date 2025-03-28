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

// Configuración de tiempos
const TIMEOUTS = {
  pageLoad: 120000, // 2 minutos para carga inicial
  iframeWait: 30000, // 30 segundos para el iframe
  betweenCaptures: 5000, // 5 segundos entre capturas
  totalDuration: 60000 // 1 minuto de capturas
};

// Función para verificar si ZeroNet está funcionando
async function isZeroNetRunning() {
  console.log('Verificando si ZeroNet está funcionando...');
  try {
    const response = await fetch('http://127.0.0.1:43110', {
      headers: { 'Accept': 'text/html' },
      timeout: 10000 // 10 segundos máximo para esta verificación
    });
    if (!response.ok) {
      console.log(`ZeroNet respondió con estado: ${response.status}`);
    }
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

  const browser = await chromium.launch({
    headless: false, // Ejecutar en modo visible para diagnóstico
    slowMo: 100 // Añadir pequeña pausa entre acciones
  });
  
  const page = await browser.newPage();
  const zeronetUrl1 = `http://127.0.0.1:43110/${zeronetAddress1}/`;

  try {
    // Configurar timeouts más largos
    page.setDefaultTimeout(TIMEOUTS.pageLoad);
    page.setDefaultNavigationTimeout(TIMEOUTS.pageLoad);

    console.log(`Navegando a: ${zeronetUrl1} (timeout: ${TIMEOUTS.pageLoad/1000}s)`);
    await page.setExtraHTTPHeaders({ 'Accept': 'text/html' });

    // Intentar cargar la página con diferentes estrategias
    const response = await page.goto(zeronetUrl1, { 
      waitUntil: 'domcontentloaded', // Más rápido que 'load'
      timeout: TIMEOUTS.pageLoad
    }).catch(async (error) => {
      console.warn(`Primer intento fallido (${error.message}), intentando con 'networkidle'`);
      return page.goto(zeronetUrl1, {
        waitUntil: 'networkidle',
        timeout: TIMEOUTS.pageLoad
      });
    });

    console.log(`Página cargada. Estado HTTP: ${response.status()}`);

    // Verificar contenido crítico
    const pageContent = await page.content();
    if (!pageContent.includes('inner-iframe')) {
      console.error('No se encuentra el elemento inner-iframe en el HTML principal');
      fs.writeFileSync(path.join(__dirname, '..', outputFolder, 'debug_main_page.html'), pageContent);
      console.log('Se ha guardado el HTML principal para diagnóstico en debug_main_page.html');
    }

    console.log('Esperando a que el iframe se cargue...');
    await page.waitForSelector('#inner-iframe', { 
      state: 'attached',
      timeout: TIMEOUTS.iframeWait 
    });

    const iframeHandle = await page.$('#inner-iframe');
    const frame = await iframeHandle.contentFrame();

    // Crear carpeta de salida
    const folderPath = path.join(__dirname, '..', outputFolder);
    if (!fs.existsSync(folderPath)) {
      fs.mkdirSync(folderPath, { recursive: true });
    }

    const ext = path.extname(outputFile);
    const baseName = path.basename(outputFile, ext);
    const iterations = TIMEOUTS.totalDuration / TIMEOUTS.betweenCaptures;

    console.log(`Iniciando captura de contenido cada ${TIMEOUTS.betweenCaptures/1000}s (${iterations} capturas)`);
    
    for (let i = 0; i < iterations; i++) {
      const startTime = Date.now();
      const sequentialFile = getSequentialFilename(folderPath, baseName, ext, i);
      
      try {
        console.log(`[${i+1}/${iterations}] Obteniendo contenido...`);
        
        // Verificar estado del iframe
        const isIframeVisible = await page.$('#inner-iframe').then(async (el) => {
          return el ? await el.isVisible() : false;
        });

        if (!isIframeVisible) {
          console.error('El iframe no está visible. Deteniendo captura.');
          break;
        }

        // Obtener contenido con timeout independiente
        const content = await frame.content().catch(e => {
          console.warn(`Error al obtener contenido del iframe: ${e.message}`);
          return "<!-- Error al obtener contenido -->";
        });

        fs.writeFileSync(sequentialFile, `<!-- Captura ${i+1} - ${new Date().toISOString()} -->\n${content}`);
        console.log(`Contenido guardado en: ${sequentialFile} (${Date.now() - startTime}ms)`);

        // Esperar para la próxima captura
        if (i < iterations - 1) {
          await new Promise(resolve => setTimeout(resolve, TIMEOUTS.betweenCaptures));
        }
      } catch (error) {
        console.error(`Error en iteración ${i+1}:`, error.message);
      }
    }
  } catch (error) {
    console.error('Error durante el proceso principal:', error.message);
    // Guardar captura de pantalla para diagnóstico
    await page.screenshot({ path: path.join(__dirname, '..', outputFolder, 'error_screenshot.png') });
    console.log('Se ha guardado una captura de pantalla del error en error_screenshot.png');
  } finally {
    await browser.close();
  }
})();
