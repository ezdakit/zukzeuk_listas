const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function captureIframeContent(url, waitMultiplier) {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Construye la URL completa con el parámetro accept
  const fullUrl = `http://127.0.0.1:43110/${url}?accept=1`;

  try {
    await page.goto(fullUrl); // Sin tiempo de espera explícito
  } catch (error) {
    console.error('Error al navegar a la página (posible timeout):', error);
    // Continuar con la ejecución, guardando los resultados parciales
  }

  // Espera a que el iframe esté presente en la página
  try {
      await page.waitForSelector('iframe#inner-iframe');
      const iframe = await page.frameLocator('iframe#inner-iframe');

      // Calcula el tiempo total de espera y el intervalo de captura.
      const totalWaitTime = waitMultiplier * 10000; // Multiplicador * 10 segundos (en milisegundos)
      const captureInterval = totalWaitTime / 10; // 10 capturas

      // Crea el directorio 'testing' si no existe
      const testingDir = path.join(__dirname, 'testing');
      if (!fs.existsSync(testingDir)) {
          fs.mkdirSync(testingDir);
      }

      // Elimina todos los archivos .html existentes en el directorio 'testing'
      fs.readdirSync(testingDir).forEach(file => {
          if (file.endsWith('.html')) {
              fs.unlinkSync(path.join(testingDir, file));
          }
      });

      // Captura el contenido del iframe y lo guarda en archivos HTML cada cierto intervalo
      for (let i = 0; i < 10; i++) {
          try {
              const content = await iframe.locator('body').innerHTML();
              const filePath = path.join(testingDir, `filename_${i}.html`);
              fs.writeFileSync(filePath, content);
          } catch (error) {
              console.error(`Error al capturar el contenido del iframe en la iteración ${i}:`, error);
              // Continuar con la siguiente iteración
          }
          await new Promise(resolve => setTimeout(resolve, captureInterval));
      }

  } catch (error) {
      console.error('Error al procesar el iFrame:', error);
  }

  await browser.close();
}

// Ejemplo de uso: captura el contenido del iframe de la URL '/13eNqJiWACUUuFM37xwUwmRiCuyMd6X2tS/?accept=1&amp;wrapper_nonce=062e6cb840397d4dd9b164fb68bbd5cb933f6eb98f46c01e9a257d624b29bb5b' y espera 30 segundos (3 * 10 segundos)
captureIframeContent('13eNqJiWACUUuFM37xwUwmRiCuyMd6X2tS/?accept=1&amp;wrapper_nonce=062e6cb840397d4dd9b164fb68bbd5cb933f6eb98f46c01e9a257d624b29bb5b', 3);
