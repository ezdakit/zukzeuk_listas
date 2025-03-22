const { chromium } = require('playwright'); // Importar Playwright
const fs = require('fs');
const path = require('path');

// Obtener los parámetros
const zeronetAddress1 = process.argv[2]; // Dirección de ZeroNet para eventos.html
const zeronetAddress2 = process.argv[3]; // Dirección de ZeroNet para lista-ott.m3u
const outputFolder = process.argv[4];    // Carpeta de destino
const outputFile = process.argv[5];     // Nombre del archivo para eventos.html

if (!zeronetAddress1 || !zeronetAddress2 || !outputFolder || !outputFile) {
  console.error('Error: Faltan parámetros. Uso: node extract-content.js <zeronet-address-1> <zeronet-address-2> <output-folder> <output-file>');
  process.exit(1);
}

// Ruta de la carpeta y el archivo
const folderPath = path.join(__dirname, outputFolder);
const filePath = path.join(folderPath, outputFile);

console.log('Parámetros recibidos:');
console.log(`- Dirección 1: ${zeronetAddress1}`);
console.log(`- Dirección 2: ${zeronetAddress2}`);
console.log(`- Carpeta de destino: ${folderPath}`);
console.log(`- Archivo de salida: ${filePath}`);

// Función para verificar si ZeroNet está funcionando
async function isZeroNetRunning() {
  console.log('Verificando si ZeroNet está funcionando...');
  try {
    const response = await fetch('http://127.0.0.1:43110', {
      headers: {
        'Accept': 'text/html', // Especificar el tipo de contenido esperado
      },
    });
    if (response.ok) {
      console.log('ZeroNet está funcionando correctamente.');
      return true;
    } else {
      console.log('ZeroNet no está funcionando (respuesta no OK).');
      return false;
    }
  } catch (error) {
    console.error('Error al verificar ZeroNet:', error.message);
    return false;
  }
}

// Función para cargar una página con reintentos
async function loadPageWithRetries(page, url, retries = 3, timeout = 60000) {
  console.log(`Cargando página: ${url}`);
  for (let i = 0; i < retries; i++) {
    try {
      console.log(`Intento ${i + 1} de ${retries}`);
      await page.goto(url, { waitUntil: 'load', timeout });
      console.log('Página cargada correctamente.');
      return true; // La página se cargó correctamente
    } catch (error) {
      console.warn(`Intento ${i + 1} fallido: ${error.message}`);
      if (i < retries - 1) {
        console.log('Reintentando en 5 segundos...');
        await new Promise((resolve) => setTimeout(resolve, 5000)); // Esperar 5 segundos antes de reintentar
      }
    }
  }
  throw new Error(`No se pudo cargar la página después de ${retries} intentos.`);
}

(async () => {
  console.log('Iniciando el script...');

  // Verificar si ZeroNet está funcionando
  if (!(await isZeroNetRunning())) {
    console.error('Error: ZeroNet no está funcionando. Saliendo...');
    process.exit(1);
  }

  // Lanzar el navegador Chromium
  console.log('Lanzando el navegador Chromium...');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  console.log('Navegador lanzado correctamente.');

  // Extraer contenido dinámico de la primera página (eventos.html)
  const zeronetUrl1 = `http://127.0.0.1:43110/${zeronetAddress1}/`;
  console.log(`Extrayendo contenido de: ${zeronetUrl1}`);

  try {
    // Configurar el encabezado "Accept" para páginas HTML
    console.log('Configurando encabezado "Accept: text/html"...');
    await page.setExtraHTTPHeaders({
      'Accept': 'text/html',
    });

    // Cargar la página con reintentos
    await loadPageWithRetries(page, zeronetUrl1);

    // Esperar a que el iframe se cargue
    console.log('Esperando a que el iframe se cargue...');
    await page.waitForSelector('#inner-iframe', { timeout: 60000 });
    console.log('Iframe cargado correctamente.');

    // Obtener el contenido del iframe
    console.log('Obteniendo el contenido del iframe...');
    const iframeHandle = await page.$('#inner-iframe');
    const frame = await iframeHandle.contentFrame();

    // Esperar a que el contenido dinámico se cargue
    console.log('Esperando a que el contenido dinámico se cargue...');
    await frame.waitForSelector('body', { timeout: 60000 });
    console.log('Contenido dinámico cargado correctamente.');

    // Obtener el HTML final del iframe
    console.log('Obteniendo el HTML final del iframe...');
    const finalContent = await frame.content();

    // Crear la carpeta si no existe
    if (!fs.existsSync(folderPath)) {
      console.log(`Creando carpeta: ${folderPath}`);
      fs.mkdirSync(folderPath, { recursive: true });
    }

    // Guardar el contenido en un archivo
    console.log(`Guardando contenido en: ${filePath}`);
    fs.writeFileSync(filePath, finalContent);
    console.log(`Archivo guardado correctamente: ${filePath}`);
  } catch (error) {
    console.error(`Error al extraer el contenido: ${error.message}`);
    process.exit(1); // Terminar el script con un código de error
  }

  // Descargar el archivo lista-ott.m3u de la segunda página
  const zeronetUrl2 = `http://127.0.0.1:43110/${zeronetAddress2}/`;
  console.log(`Sincronizando contenido de: ${zeronetUrl2}`);

  try {
    // Configurar el encabezado "Accept" para la descarga del archivo
    console.log('Configurando encabezado "Accept: */*"...');
    await page.setExtraHTTPHeaders({
      'Accept': '*/*', // Aceptar cualquier tipo de contenido para la descarga
    });

    // Cargar la página con reintentos
    await loadPageWithRetries(page, zeronetUrl2);

    const downloadUrl = `http://127.0.0.1:43110/${zeronetAddress2}/lista-ott.m3u`;
    console.log(`Descargando archivo: ${downloadUrl}`);
    const response = await page.goto(downloadUrl, { waitUntil: 'load', timeout: 60000 });

    if (response.status() === 200) {
      console.log('Archivo descargado correctamente.');
      const content = await response.text();
      const downloadPath = path.join(folderPath, 'lista-ott.m3u');
      console.log(`Guardando archivo en: ${downloadPath}`);
      fs.writeFileSync(downloadPath, content);
      console.log(`Archivo guardado correctamente: ${downloadPath}`);
    } else {
      console.error(`Error al descargar el archivo: ${response.status()}`);
    }
  } catch (error) {
    console.error(`Error al descargar el archivo: ${error.message}`);
    process.exit(1); // Terminar el script con un código de error
  }

  // Cerrar el navegador
  console.log('Cerrando el navegador...');
  await browser.close();
  console.log('Navegador cerrado correctamente.');

  console.log('Script completado con éxito.');
})();
