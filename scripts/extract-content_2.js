const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Obtener los parámetros
const zeronetAddress = process.argv[2];
const outputFolder = process.argv[3];
const outputFile = process.argv[4];

if (!zeronetAddress || !outputFolder || !outputFile) {
  console.error('Error: Faltan parámetros. Uso: node extract-content.js <zeronet-address> <output-folder> <output-file>');
  process.exit(1);
}

// Ruta de la carpeta y el archivo
const folderPath = path.join(__dirname, '..', outputFolder);
const filePath = path.join(folderPath, outputFile);

console.log('Parámetros recibidos:');
console.log(`- Dirección: ${zeronetAddress}`);
console.log(`- Carpeta de destino: ${folderPath}`);
console.log(`- Archivo de salida: ${filePath}`);

// Función para verificar si ZeroNet está funcionando
async function isZeroNetRunning() {
  console.log('Verificando si ZeroNet está funcionando...');
  try {
    const response = await fetch('http://127.0.0.1:43110', {
      headers: {
        'Accept': 'text/html',
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
      return true;
    } catch (error) {
      console.warn(`Intento ${i + 1} fallido: ${error.message}`);
      if (i < retries - 1) {
        console.log('Reintentando en 5 segundos...');
        await new Promise((resolve) => setTimeout(resolve, 5000));
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

  // Extraer contenido inicial de la página
  const zeronetUrl = `http://127.0.0.1:43110/${zeronetAddress}/`;
  console.log(`Extrayendo contenido de: ${zeronetUrl}`);

  try {
    // Configurar el encabezado "Accept" para páginas HTML
    console.log('Configurando encabezado "Accept: text/html"...');
    await page.setExtraHTTPHeaders({
      'Accept': 'text/html',
    });

    // Cargar la página con reintentos
    await loadPageWithRetries(page, zeronetUrl);

    // Obtener el HTML inicial de la página
    console.log('Obteniendo el HTML inicial de la página...');
    const initialContent = await page.content();

    // Crear la carpeta si no existe
    if (!fs.existsSync(folderPath)) {
      console.log(`Creando carpeta: ${folderPath}`);
      fs.mkdirSync(folderPath, { recursive: true });
    }

    // Guardar el contenido en un archivo
    console.log(`Guardando contenido en: ${filePath}`);
    fs.writeFileSync(filePath, initialContent);
    console.log(`Archivo guardado correctamente: ${filePath}`);
  } catch (error) {
    console.error(`Error al extraer el contenido: ${error.message}`);
    process.exit(1);
  }

  // Cerrar el navegador
  console.log('Cerrando el navegador...');
  await browser.close();
  console.log('Navegador cerrado correctamente.');
  console.log('Script completado con éxito.');
})();
