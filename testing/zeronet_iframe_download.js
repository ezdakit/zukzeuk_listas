const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function captureIframeContent(url, waitMultiplier) {
  console.log('Iniciando captura de contenido del iframe...');

  const browser = await chromium.launch();
  const page = await browser.newPage();

  console.log('Navegador iniciado.');

  // Construye la URL completa con el parámetro accept
  const fullUrl = `http://127.0.0.1:43110/${url}?accept=1`;

  console.log(`Navegando a: ${fullUrl}`);

  try {
    await page.goto(fullUrl, { timeout: 0 }); // Desactiva el tiempo de espera
    console.log('Navegación completada con éxito.');
  } catch (error) {
    console.error('Error al navegar a la página (posible timeout, pero ignorado):', error);
    // Continuar con la ejecución, incluso si la navegación falla
  }

  try {
      console.log('Esperando selector del iframe');
      await page.waitForSelector('iframe#inner-iframe', {timeout: 60000}); //60 seconds timeout
      const iframe = await page.frameLocator('iframe#inner-iframe');
      console.log('Selector del iframe encontrado');

      // Calcula el tiempo total de espera y el intervalo de captura.
      const totalWaitTime = waitMultiplier * 10000; // Multiplicador * 10 segundos (en milisegundos)
      const captureInterval = totalWaitTime / 10; // 10 capturas

      console.log(`Tiempo total de espera: ${totalWaitTime}ms`);
      console.log(`Intervalo de captura: ${captureInterval}ms`);

      // Crea el directorio 'testing' si no existe
      const testingDir = path.join(__dirname, 'testing');
      if (!fs.existsSync(testingDir)) {
          fs.mkdirSync(testingDir);
          console.log(`Directorio '${testingDir}' creado.`);
      }

      // Elimina todos los archivos .html existentes en el directorio 'testing'
      fs.readdirSync(testingDir).forEach(file => {
          if (file.endsWith('.html')) {
              fs.unlinkSync(path.join(testingDir, file));
              console.log(`Archivo '${file}' eliminado.`);
          }
      });

      // Captura el contenido del iframe y lo guarda en archivos HTML cada cierto intervalo
      for (let i = 0; i < 10; i++) {
          try {
              const content = await iframe.locator('body').innerHTML();
              const filePath = path.join(testingDir, `filename_${i}.html`);
              fs.writeFileSync(filePath, content);
              console.log(`Contenido capturado y guardado en '${filePath}'.`);
          } catch (error) {
              console.error(`Error al capturar el contenido del iframe en la iteración ${i}:`, error);
              // Continuar con la siguiente iteración
          }
          await new Promise(resolve => setTimeout(resolve, captureInterval));
      }

  } catch (error) {
      console.error('Error al procesar el iFrame:', error);
  }

  console.log('Cerrando el navegador.');
  await browser.close();

  console.log('Captura de contenido del iframe completada.');
}

// Ejemplo de uso: captura el contenido del iframe de la URL '/13eNqJiWACUUuFM37xwUwmRiCuyMd6X2tS/?accept=1&amp;wrapper_nonce=062e6cb840397d4dd9b164fb68bbd5cb933f6eb98f46c01e9a257d624b29bb5b' y espera 30 segundos (3 * 10 segundos)
captureIframeContent('13eNqJiWACUUuFM37xwUwmRiCuyMd6X2tS/?accept=1&amp;wrapper_nonce=062e6cb840397d4dd9b164fb68bbd5cb933f6eb98f46c01e9a257d624b29bb5b', 3);
