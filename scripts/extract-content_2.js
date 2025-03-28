const { chromium } = require('playwright');

// Obtener los parámetros
const zeronetAddress = process.argv[2];

if (!zeronetAddress) {
  console.error('Error: Falta el parámetro de la dirección de ZeroNet. Uso: node extract-content.js <zeronet-address>');
  process.exit(1);
}

const zeronetUrl = `http://127.0.0.1:43110/${zeronetAddress}/`;

(async () => {
  console.log('Iniciando el script...');
  console.log(`Navegando a ${zeronetUrl}...`);

  // Lanzar el navegador Chromium
  const browser = await chromium.launch();
  const page = await browser.newPage();

  try {
    // Intentar cargar la página
    await page.goto(zeronetUrl, { waitUntil: 'load', timeout: 60000 });
    console.log('Página cargada correctamente.');
  } catch (error) {
    console.error(`Ha ocurrido un error: ${error}`);
  } finally {
    // Cerrar el navegador
    await browser.close();
    console.log('Navegador cerrado.');
  }
})();
