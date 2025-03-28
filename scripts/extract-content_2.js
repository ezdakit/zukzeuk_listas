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
  const page = await browser.newPage();
  
  try {
    const zeronetUrl = `http://127.0.0.1:43110/${zeronetAddress}/`;
    console.log(`Extrayendo contenido de: ${zeronetUrl}`);

    // Configuración con tiempos de espera extendidos
    await page.goto(zeronetUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 120000 // 2 minutos para cargar la página
    });

    console.log('Página cargada, esperando contenido...');

    // Estrategia de espera flexible
    try {
      // Esperar a que haya algún contenido visible en el body
      await page.waitForFunction(() => {
        const bodyText = document.body.innerText;
        return bodyText && bodyText.trim().length > 100;
      }, { timeout: 60000 });

      console.log('Contenido detectado en la página');

      // Tomar captura de pantalla para diagnóstico
      await page.screenshot({ path: path.join(folderPath, 'debug.png') });
      console.log('Captura de pantalla guardada en debug.png');

      // Verificar si la tabla de eventos existe (pero no fallar si no)
      const tableExists = await page.evaluate(() => {
        return !!document.querySelector('#events-table');
      });

      if (tableExists) {
        console.log('Tabla de eventos encontrada');
      } else {
        console.warn('Advertencia: No se encontró la tabla #events-table');
        // Listar todos los IDs y clases presentes para diagnóstico
        const pageStructure = await page.evaluate(() => {
          const ids = Array.from(document.querySelectorAll('[id]')).map(el => el.id);
          const classes = Array.from(document.querySelectorAll('[class]')).flatMap(el => el.className.split(' '));
          return { ids, classes };
        });
        console.log('Estructura de la página:', JSON.stringify(pageStructure, null, 2));
      }

      // Extraer el HTML completo
      const content = await page.content();
      
      // Crear la carpeta si no existe
      if (!fs.existsSync(folderPath)) {
        fs.mkdirSync(folderPath, { recursive: true });
      }

      // Guardar el contenido
      fs.writeFileSync(filePath, content);
      console.log(`Contenido guardado en: ${filePath}`);

      // Verificación final
      if (content.includes('events-table')) {
        console.log('Éxito: La tabla de eventos está en el contenido guardado');
      } else {
        console.warn('Advertencia: No se detectó la tabla en el HTML guardado');
        console.warn('Primeras 500 caracteres del contenido:', content.substring(0, 500));
      }

    } catch (error) {
      console.error('Error durante la extracción:', error);
      // Guardar el contenido de todos modos para diagnóstico
      const fallbackContent = await page.content();
      if (!fs.existsSync(folderPath)) {
        fs.mkdirSync(folderPath, { recursive: true });
      }
      fs.writeFileSync(filePath, fallbackContent);
      console.log('Se guardó contenido de fallback para diagnóstico');
      // No salir con error para permitir inspección del contenido
    }

  } catch (error) {
    console.error('Error fatal:', error);
    process.exit(1);
  } finally {
    await browser.close();
    console.log('Navegador cerrado');
  }
})();
