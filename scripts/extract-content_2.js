const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Configuración optimizada para ZeroNet
const CONFIG = {
  NAVIGATION_TIMEOUT: 600000, // 10 minutos
  ACTION_TIMEOUT: 300000,     // 5 minutos
  RETRY_DELAY: 20000,         // 20 segundos
  MAX_RETRIES: 5,             // 5 reintentos
  FINAL_WAIT: 15000           // 15 segundos adicionales
};

// Validación de parámetros
const [,, zeronetAddress, outputFolder, outputFile] = process.argv;
if (!zeronetAddress || !outputFolder || !outputFile) {
  console.error('Uso: node script.js <zeronet-address> <output-folder> <output-file>');
  process.exit(1);
}

const folderPath = path.join(__dirname, '..', outputFolder);
const filePath = path.join(folderPath, outputFile);

// Función con reintentos seguros sin eval
async function safeRetryOperation(operation, description) {
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

// Verificador de visibilidad seguro
async function isElementVisible(pageOrFrame, selector) {
  return await pageOrFrame.$eval(selector, el => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    return style && style.display !== 'none' && style.visibility !== 'hidden' && el.offsetWidth > 0 && el.offsetHeight > 0;
  }).catch(() => false);
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

    // 1. Navegación inicial (sin verificación de readyState)
    await safeRetryOperation(
      () => page.goto(targetUrl, { 
        waitUntil: 'domcontentloaded',
        timeout: CONFIG.NAVIGATION_TIMEOUT 
      }),
      'Navegando a la página'
    );

    // 2. Esperar iframe principal usando métodos seguros
    console.log('Esperando iframe principal...');
    await safeRetryOperation(
      async () => {
        await page.waitForSelector('#inner-iframe', { 
          state: 'attached',
          timeout: CONFIG.ACTION_TIMEOUT 
        });
        
        const isVisible = await isElementVisible(page, '#inner-iframe');
        if (!isVisible) throw new Error('El iframe no está visible');
      },
      'Localizando iframe'
    );

    // 3. Acceder al contenido del iframe
    const frame = await page.$('#inner-iframe').then(f => f.contentFrame());
    if (!frame) {
      throw new Error('No se pudo acceder al contenido del iframe');
    }

    // 4. Esperar contenido dinámico con verificación segura
    console.log('Esperando contenido dinámico...');
    
    await safeRetryOperation(
      async () => {
        // Verificar que la tabla existe
        await frame.waitForSelector('#events-table', {
          state: 'attached',
          timeout: CONFIG.ACTION_TIMEOUT
        });
        
        // Verificar que tiene filas visibles
        const hasVisibleRows = await frame.$$eval(
          '#events-table tbody tr',
          rows => rows.some(r => r.offsetParent !== null && r.textContent.trim().length > 0)
        );
        
        if (!hasVisibleRows) throw new Error('Tabla sin filas visibles o con contenido');
      },
      'Verificando tabla con datos'
    );

    // Espera final para asegurar renderizado completo
    console.log('Espera final para renderizado completo...');
    await page.waitForTimeout(CONFIG.FINAL_WAIT);

    // 5. Extraer contenido HTML
    console.log('Extrayendo contenido final...');
    const finalContent = await frame.content();

    // 6. Guardar archivo
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
