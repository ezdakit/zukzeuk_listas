const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Configuración ajustada para ZeroNet
const CONFIG = {
  NAVIGATION_TIMEOUT: 600000, // 10 minutos
  ACTION_TIMEOUT: 300000,     // 5 minutos
  RETRY_DELAY: 20000,         // 20 segundos
  MAX_RETRIES: 5,             // 5 reintentos
  FINAL_WAIT: 10000           // 10 segundos adicionales
};

// Validación de parámetros
const [,, zeronetAddress, outputFolder, outputFile] = process.argv;
if (!zeronetAddress || !outputFolder || !outputFile) {
  console.error('Uso: node script.js <zeronet-address> <output-folder> <output-file>');
  process.exit(1);
}

const folderPath = path.join(__dirname, '..', outputFolder);
const filePath = path.join(folderPath, outputFile);

// Función con reintentos inteligentes
async function robustOperation(operation, description) {
  let lastError;
  
  for (let attempt = 1; attempt <= CONFIG.MAX_RETRIES; attempt++) {
    try {
      console.log(`${description} [Intento ${attempt}/${CONFIG.MAX_RETRIES}]`);
      const result = await operation();
      return result;
    } catch (error) {
      lastError = error;
      console.warn(`Intento ${attempt} fallido: ${error.message}`);
      
      if (attempt < CONFIG.MAX_RETRIES) {
        console.log(`Reintentando en ${CONFIG.RETRY_DELAY/1000} segundos...`);
        await new Promise(resolve => setTimeout(resolve, CONFIG.RETRY_DELAY));
      }
    }
  }
  
  throw lastError;
}

async function extractZeroNetContent() {
  const browser = await chromium.launch({ 
    headless: true,
    timeout: CONFIG.NAVIGATION_TIMEOUT
  });
  
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // Configuración de timeouts
    page.setDefaultTimeout(CONFIG.ACTION_TIMEOUT);
    page.setDefaultNavigationTimeout(CONFIG.NAVIGATION_TIMEOUT);

    const targetUrl = `http://127.0.0.1:43110/${zeronetAddress}/`;
    console.log(`Target URL: ${targetUrl}`);

    // 1. Navegación inicial
    await robustOperation(
      () => page.goto(targetUrl, { 
        waitUntil: 'domcontentloaded',
        timeout: CONFIG.NAVIGATION_TIMEOUT 
      }),
      'Navegando a la página'
    );

    // 2. Esperar señal de carga completa
    console.log('Esperando señal de carga completa...');
    await robustOperation(
      () => page.waitForFunction(
        () => document.readyState === 'complete',
        { timeout: CONFIG.ACTION_TIMEOUT }
      ),
      'Verificando estado de carga'
    );

    // 3. Localizar y verificar iframe principal
    console.log('Buscando iframe principal...');
    await robustOperation(
      () => page.waitForSelector('#inner-iframe', { 
        state: 'attached',
        timeout: CONFIG.ACTION_TIMEOUT 
      }),
      'Localizando iframe'
    );

    // 4. Verificar visibilidad del iframe (sin evaluar JS)
    const isIframeVisible = await page.evaluate(() => {
      const iframe = document.getElementById('inner-iframe');
      if (!iframe) return false;
      const style = window.getComputedStyle(iframe);
      return style && style.display !== 'none' && style.visibility !== 'hidden';
    });

    if (!isIframeVisible) {
      throw new Error('El iframe no está visible en la página');
    }

    // 5. Acceder al contenido del iframe
    const frame = await page.$('#inner-iframe').then(f => f.contentFrame());
    if (!frame) {
      throw new Error('No se pudo acceder al contenido del iframe');
    }

    // 6. Esperar contenido dinámico con verificación en dos pasos
    console.log('Esperando contenido dinámico...');
    
    // Paso 6.1: Esperar estructura de tabla
    await robustOperation(
      () => frame.waitForSelector('#events-table', {
        state: 'attached',
        timeout: CONFIG.ACTION_TIMEOUT
      }),
      'Esperando estructura de tabla'
    );

    // Paso 6.2: Esperar datos visibles
    await robustOperation(
      async () => {
        const hasVisibleRows = await frame.$$eval(
          '#events-table tbody tr',
          rows => rows.some(r => r.offsetParent !== null)
        );
        if (!hasVisibleRows) throw new Error('Tabla sin filas visibles');
      },
      'Verificando filas visibles'
    );

    // Espera final para asegurar renderizado completo
    console.log('Espera final para renderizado completo...');
    await page.waitForTimeout(CONFIG.FINAL_WAIT);

    // 7. Extraer contenido HTML
    console.log('Extrayendo contenido final...');
    const finalContent = await frame.content();

    // 8. Guardar archivo
    if (!fs.existsSync(folderPath)) {
      fs.mkdirSync(folderPath, { recursive: true });
    }
    fs.writeFileSync(filePath, finalContent);
    console.log(`✅ Contenido guardado en: ${filePath}`);

  } catch (error) {
    console.error('❌ Error crítico:', error);
    throw error;
  } finally {
    await browser.close();
    console.log('Navegador cerrado');
  }
}

// Ejecución con manejo de errores global
extractZeroNetContent()
  .then(() => process.exit(0))
  .catch(error => {
    console.error('🛑 Fallo en el proceso de extracción:', error.message);
    process.exit(1);
  });
