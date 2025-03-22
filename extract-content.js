const { chromium } = require('playwright'); // Importar Playwright
const fs = require('fs');

(async () => {
  // Lanzar el navegador Chromium
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const url = 'http://127.0.0.1:43110/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie/';

  // Navegar a la URL
  await page.goto(url, { waitUntil: 'networkidle' });

  // Esperar a que el iframe se cargue
  await page.waitForSelector('#inner-iframe');

  // Obtener el contenido del iframe
  const iframeHandle = await page.$('#inner-iframe');
  const frame = await iframeHandle.contentFrame();

  // Esperar a que el contenido dinámico se cargue
  await frame.waitForSelector('body');

  // Obtener el HTML final del iframe
  const finalContent = await frame.content();

  // Guardar el contenido en un archivo
  fs.writeFileSync('final-content.html', finalContent);

  // Cerrar el navegador
  await browser.close();
})();
