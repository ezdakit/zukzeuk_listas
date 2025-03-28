const { chromium } = require('playwright');
const fs = require('node:fs/promises');

async function downloadZeroNetContent(zeronetAddress, outputFilename) {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  const url = `http://127.0.0.1:43110/${zeronetAddress}`;

  try {
    console.log(`Navegando a ${url}...`);
    await page.goto(url, { timeout: 60000 }); // Aumento del tiempo de espera por posible latencia

    console.log('Extrayendo contenido HTML...');
    const htmlContent = await page.content();

    console.log(`Guardando contenido HTML en ${outputFilename}...`);
    await fs.writeFile(outputFilename, htmlContent, 'utf8');
    console.log(`Contenido HTML guardado en ${outputFilename}`);

  } catch (error) {
    console.error(`Ha ocurrido un error: ${error}`);
  } finally {
    await browser.close();
  }
}

const zeronetAddress = '13eNqJiWACUUuFM37xwUwmRiCuyMd6X2tS';
const outputFilename = 'eventos_2.html';

downloadZeroNetContent(zeronetAddress, outputFilename);
