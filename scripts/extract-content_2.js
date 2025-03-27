const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Configuración de timeouts (en milisegundos)
const CONFIG = {
  NAVIGATION_TIMEOUT: 300000, // 5 minutos para navegación
  DEFAULT_TIMEOUT: 120000,    // 2 minutos para otras operaciones
  RETRY_DELAY: 10000,        // 10 segundos entre reintentos
  MAX_RETRIES: 3             // Máximo de reintentos
};

// Obtener parámetros
const [,, zeronetAddress, outputFolder, outputFile] = process.argv;

if (!zeronetAddress || !outputFolder || !outputFile) {
  console.error('Uso: node script.js <zeronet-address> <output-folder> <output-file>');
  process.exit(1);
}

const folderPath = path.join(__dirname, '..', outputFolder);
const filePath = path.join(folderPath, outputFile);

async function withRetries(fn, description, maxRetries = CONFIG.MAX_RETRIES) {
  let lastError;
  for (let i = 0; i < maxRetries; i++) {
    try {
      console.log(`${description} (Intento ${i + 1}/${maxRetries})`);
      return await fn();
    } catch (error) {
      lastError = error;
      if (i < maxRetries - 1) {
        await new Promise(resolve => setTimeout(resolve, CONFIG.RETRY_DELAY));
      }
    }
  }
  throw lastError;
}

async function extractContent() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // Configurar timeouts
    page.setDefaultTimeout(CONFIG.DEFAULT_TIMEOUT);
    page.setDefaultNavigationTimeout(CONFIG.NAVIGATION_TIMEOUT);

    const url = `http://127.0.0.1:43110/${zeronetAddress}/`;
    console.log(`Iniciando extracción de: ${url}`);

    // Paso 1: Navegar a la página
    await withRetries(
      () => page.goto(url, { waitUntil: 'domcontentloaded' }),
      'Navegando a la página'
    );

    // Paso 2: Esperar indicadores de carga
    console.log('Esperando indicadores de carga...');
    await withRetries(
      () => page.waitForSelector('#inner-iframe', { state: 'attached' }),
      'Esperando iframe principal'
    );

    // Paso 3: Verificar iframe visible
    const isIframeReady = await page.evaluate(() => {
      const iframe = document.querySelector('#inner-iframe');
      return iframe && iframe.offsetWidth > 0 && iframe.offsetHeight > 0;
    });
    
    if (!isIframeReady) {
      throw new Error('El iframe no está listo para interactuar');
    }

    // Paso 4: Acceder al contenido del iframe
    const frame = await (await page.$('#inner-iframe')).contentFrame();
    
    // Paso 5: Esperar contenido dinámico
    console.log('Esperando contenido dinámico...');
    await withRetries(
      () => frame.waitForSelector('#events-table', { state: 'visible' }),
      'Esperando tabla de eventos'
    );

    // Paso 6: Esperar datos cargados (verificar filas)
    await withRetries(
      async () => {
        const hasData = await frame.$$eval('#events-table tbody tr', rows => rows.length > 0);
        if (!hasData) throw new Error('La tabla no contiene datos');
      },
      'Verificando datos en la tabla'
    );

    // Paso 7: Obtener HTML final
    console.log('Obteniendo contenido final...');
    const content = await frame.content();

    // Guardar archivo
    if (!fs.existsSync(folderPath)) {
      fs.mkdirSync(folderPath, { recursive: true });
    }
    fs.writeFileSync(filePath, content);
    console.log(`Contenido guardado en: ${filePath}`);

  } finally {
    await browser.close();
  }
}

// Ejecutar con manejo de errores
extractContent()
  .then(() => process.exit(0))
  .catch(error => {
    console.error('Error en el proceso de extracción:', error);
    process.exit(1);
  });
