const puppeteer = require('puppeteer');
const fs = require('fs');

(async () => {
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  const url = 'http://127.0.0.1:43110/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie/';
  await page.goto(url, { waitUntil: 'networkidle2' });

  // Esperar a que el iframe se cargue
  await page.waitForSelector('#inner-iframe');

  // Obtener el contenido del iframe
  const frameHandle = await page.$('#inner-iframe');
  const frame = await frameHandle.contentFrame();

  // Esperar a que el contenido dinámico se cargue
  await frame.waitForSelector('body');

  // Obtener el HTML final del iframe
  const finalContent = await frame.content();

  // Guardar el contenido en un archivo
  fs.writeFileSync('final-content.html', finalContent);

  await browser.close();
})();
