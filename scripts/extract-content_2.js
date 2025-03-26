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

(async () => {
  console.log('Iniciando el script...');
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  try {
    const zeronetUrl = `http://127.0.0.1:43110/${zeronetAddress}/`;
    console.log(`Extrayendo contenido de: ${zeronetUrl}`);

    // 1. Cargar página principal
    await page.goto(zeronetUrl, { waitUntil: 'domcontentloaded', timeout: 120000 });

    // 2. Esperar iframe
    await page.waitForSelector('#inner-iframe', { timeout: 30000 });
    const frameHandle = await page.$('#inner-iframe');
    const frame = await frameHandle.contentFrame();

    // 3. Estrategia de espera mejorada para contenido del iframe
    let attempts = 0;
    const maxAttempts = 3;
    let success = false;

    while (attempts < maxAttempts && !success) {
      attempts++;
      console.log(`Intento ${attempts} de ${maxAttempts}`);
      
      try {
        // Opción 1: Esperar a que aparezca la tabla directamente
        await frame.waitForSelector('#events-table', { timeout: 30000 });
        success = true;
      } catch (e) {
        console.log('Tabla no encontrada, intentando alternativa...');
        
        // Opción 2: Verificar si hay algún contenido útil
        const hasContent = await frame.evaluate(() => {
          return document.body.innerText.length > 100;
        });
        
        if (hasContent) {
          console.log('Se encontró contenido alternativo en el iframe');
          success = true;
        } else {
          // Opción 3: Recargar el iframe
          await frame.evaluate(() => location.reload());
          await new Promise(resolve => setTimeout(resolve, 5000));
        }
      }
    }

    if (!success) {
      throw new Error('No se pudo cargar el contenido después de varios intentos');
    }

    // 4. Extraer contenido
    const content = await frame.content();
    
    // 5. Guardar resultados
    if (!fs.existsSync(folderPath)) {
      fs.mkdirSync(folderPath, { recursive: true });
    }
    fs.writeFileSync(filePath, content);
    console.log(`Contenido guardado en: ${filePath}`);

    // 6. Verificación final
    if (content.includes('events-table')) {
      console.log('Éxito: Tabla encontrada');
    } else {
      console.warn('Advertencia: La tabla no está en el contenido');
      // Guardar diagnóstico extendido
      const diagnostics = {
        url: zeronetUrl,
        timestamp: new Date().toISOString(),
        contentSample: content.substring(0, 500),
        fullPage: await page.content()
      };
      fs.writeFileSync(path.join(folderPath, 'diagnostics.json'), JSON.stringify(diagnostics, null, 2));
    }

  } catch (error) {
    console.error('Error crítico:', error);
    // Guardar toda la información disponible para diagnóstico
    const errorData = {
      error: error.toString(),
      pageContent: await page?.content?.(),
      timestamp: new Date().toISOString()
    };
    fs.writeFileSync(path.join(folderPath, 'error.json'), JSON.stringify(errorData, null, 2));
    process.exit(1);
  } finally {
    await browser.close();
    console.log('Navegador cerrado');
  }
})();
