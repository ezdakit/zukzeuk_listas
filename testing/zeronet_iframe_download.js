const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function captureIframeContent(url) {
  console.log('Iniciando captura de contenido del iframe...');

  const browser = await chromium.launch();
  const page = await browser.newPage();

  console.log('Navegador iniciado.');

  // Construye la URL completa con el parámetro accept
  const fullUrl = `${url}?accept=1`;

  console.log(`Navegando a: ${fullUrl}`);

  try {
    await page.goto(fullUrl, { timeout: 10000 }); // 10s el tiempo de espera
    console.log('Navegación completada con éxito.');
  } catch (error) {
    console.error('Error al navegar a la página:', error);
    // Continuar con la ejecución, incluso si la navegación falla
  }

  try {
      console.log('Esperando selector del iframe');
      await page.waitForSelector('iframe#inner-iframe', {timeout: 10000}); //10 seconds timeout
      const iframe = await page.frameLocator('iframe#inner-iframe');
      console.log('Selector del iframe encontrado');

      // Espera explícita para asegurar que el contenido dinámico se cargue
      await page.waitForTimeout(10000); // Espera 10 segundos

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

      try {
          const content = await iframe.locator('body').innerHTML();
          const filePath = path.join(testingDir, `iframe.html`);
          fs.writeFileSync(filePath, content);
          console.log(`Contenido capturado y guardado en '${filePath}'.`);
      } catch (error) {
          console.error(`Error al capturar el contenido del iframe`, error);
      }

  } catch (error) {
      console.error('Error al procesar el iFrame:', error);
  }
  
  console.log('Cerrando el navegador.');
  await browser.close();

  console.log('Captura de contenido del iframe completada.');
}

// Obtener los argumentos de la línea de comandos
const url = process.argv[2];
captureIframeContent(url);
