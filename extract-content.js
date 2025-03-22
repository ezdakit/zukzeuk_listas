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

(async () => {
  // Lanzar el navegador Chromium
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Configurar el encabezado "Accept"
  await page.setExtraHTTPHeaders({
    'Accept': 'text/html',
  });

  // Extraer contenido dinámico de la primera página (eventos.html)
  const zeronetUrl1 = `http://127.0.0.1:43110/${zeronetAddress1}/`;
  console.log(`Extrayendo contenido de: ${zeronetUrl1}`);

  try {
    // Aumentar el tiempo de espera a 60 segundos y usar 'load' en lugar de 'networkidle'
    await page.goto(zeronetUrl1, { waitUntil: 'load', timeout: 60000 });

    // Esperar a que el iframe se cargue
    await page.waitForSelector('#inner-iframe', { timeout: 60000 });

    // Obtener el contenido del iframe
    const iframeHandle = await page.$('#inner-iframe');
    const frame = await iframeHandle.contentFrame();

    // Esperar a que el contenido dinámico se cargue
    await frame.waitForSelector('body', { timeout: 60000 });

    // Obtener el HTML final del iframe
    const finalContent = await frame.content();

    // Crear la carpeta si no existe
    if (!fs.existsSync(folderPath)) {
      fs.mkdirSync(folderPath, { recursive: true });
    }

    // Guardar el contenido en un archivo
    fs.writeFileSync(filePath, finalContent);
    console.log(`Archivo guardado en: ${filePath}`);
  } catch (error) {
    console.error(`Error al extraer el contenido: ${error.message}`);
    process.exit(1); // Terminar el script con un código de error
  }

  // Descargar el archivo lista-ott.m3u de la segunda página
  const zeronetUrl2 = `http://127.0.0.1:43110/${zeronetAddress2}/`;
  console.log(`Sincronizando contenido de: ${zeronetUrl2}`);

  try {
    // Aumentar el tiempo de espera a 60 segundos y usar 'load' en lugar de 'networkidle'
    await page.goto(zeronetUrl2, { waitUntil: 'load', timeout: 60000 });

    const downloadUrl = `http://127.0.0.1:43110/${zeronetAddress2}/lista-ott.m3u`;
    console.log(`Descargando archivo: ${downloadUrl}`);
    const response = await page.goto(downloadUrl, { waitUntil: 'load', timeout: 60000 });

    if (response.status() === 200) {
      const content = await response.text();
      const downloadPath = path.join(folderPath, 'lista-ott.m3u');
      fs.writeFileSync(downloadPath, content);
      console.log(`Archivo descargado en: ${downloadPath}`);
    } else {
      console.error(`Error al descargar el archivo: ${response.status()}`);
    }
  } catch (error) {
    console.error(`Error al descargar el archivo: ${error.message}`);
    process.exit(1); // Terminar el script con un código de error
  }

  // Cerrar el navegador
  await browser.close();
})();
