const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Obtener los parámetros
const zeronetAddress = process.argv[2]; // Dirección de ZeroNet (13eNqJiWACUUuFM37xwUwmRiCuyMd6X2tS)
const outputFolder = process.argv[3];   // Carpeta de destino
const outputFile = process.argv[4];     // Nombre del archivo para eventos_2.html

if (!zeronetAddress || !outputFolder || !outputFile) {
  console.error('Error: Faltan parámetros. Uso: node extract-events.js <zeronet-address> <output-folder> <output-file>');
  process.exit(1);
}

// Ruta de la carpeta y el archivo
const folderPath = path.join(__dirname, '..', outputFolder);
const filePath = path.join(folderPath, outputFile);

console.log('Parámetros recibidos:');
console.log(`- Dirección ZeroNet: ${zeronetAddress}`);
console.log(`- Carpeta de destino: ${folderPath}`);
console.log(`- Archivo de salida: ${filePath}`);

async function isZeroNetRunning() {
  console.log('Verificando si ZeroNet está funcionando...');
  try {
    const response = await fetch('http://127.0.0.1:43110', {
      headers: { 'Accept': 'text/html' },
    });
    if (response.ok) {
      console.log('ZeroNet está funcionando correctamente.');
      return true;
    }
    console.log('ZeroNet no está funcionando (respuesta no OK).');
    return false;
  } catch (error) {
    console.error('Error al verificar ZeroNet:', error.message);
    return false;
  }
}

async function loadPageWithRetries(page, url, retries = 3, timeout = 60000) {
  console.log(`Cargando página: ${url}`);
  for (let i = 0; i < retries; i++) {
    try {
      console.log(`Intento ${i + 1} de ${retries}`);
      await page.goto(url, { 
        waitUntil: 'networkidle', // Más estricto que 'domcontentloaded'
        timeout 
      });
      console.log('Página cargada correctamente.');
      return true;
    } catch (error) {
      console.warn(`Intento ${i + 1} fallido: ${error.message}`);
      if (i < retries - 1) {
        console.log('Reintentando en 5 segundos...');
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }
  }
  throw new Error(`No se pudo cargar la página después de ${retries} intentos.`);
}

(async () => {
  console.log('Iniciando el script...');

  if (!(await isZeroNetRunning())) {
    console.error('Error: ZeroNet no está funcionando. Saliendo...');
    process.exit(1);
  }

  console.log('Lanzando el navegador Chromium...');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  console.log('Navegador lanzado correctamente.');

  const zeronetUrl = `http://127.0.0.1:43110/${zeronetAddress}/`;
  console.log(`Extrayendo contenido de: ${zeronetUrl}`);

  try {
    await page.setExtraHTTPHeaders({ 'Accept': 'text/html' });

    // Cargar la página con reintentos
    await loadPageWithRetries(page, zeronetUrl);

    // Esperar directamente a que la tabla esté presente
    console.log('Esperando a que la tabla "events-table" se cargue...');
    await page.waitForSelector('#events-table', { 
      timeout: 30000,
      state: 'attached'
    });

    // Verificar que la tabla tenga contenido (filas)
    console.log('Verificando que la tabla tenga datos...');
    await page.waitForFunction(() => {
      const table = document.querySelector('#events-table tbody');
      return table && table.querySelectorAll('tr').length > 0;
    }, { timeout: 20000 });

    console.log('Tabla "events-table" cargada con datos.');

    // Opcional: Esperar a que los eventos próximos estén visibles
    await page.waitForSelector('.status.pronto', { timeout: 10000 });

    // Extraer solo la sección relevante (opcional)
    const tableHtml = await page.$eval('.table-container', container => {
      // Puedes personalizar esto para extraer solo lo que necesites
      return container.outerHTML;
    });

    // O extraer toda la página si lo prefieres
    const fullHtml = await page.content();

    // Crear la carpeta si no existe
    if (!fs.existsSync(folderPath)) {
      console.log(`Creando carpeta: ${folderPath}`);
      fs.mkdirSync(folderPath, { recursive: true });
    }

    // Guardar el contenido (elige una de las opciones)
    console.log(`Guardando contenido en: ${filePath}`);
    fs.writeFileSync(filePath, fullHtml); // o tableHtml si elegiste extraer solo la tabla
    console.log(`Archivo guardado correctamente: ${filePath}`);

  } catch (error) {
    console.error(`Error al extraer el contenido: ${error.message}`);
    process.exit(1);
  } finally {
    console.log('Cerrando el navegador...');
    await browser.close();
    console.log('Navegador cerrado correctamente.');
  }

  console.log('Script completado con éxito.');
})();
