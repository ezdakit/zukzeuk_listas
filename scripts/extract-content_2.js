const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Obtener los parámetros
const zeronetAddress = process.argv[2];
const outputFolder = process.argv[3];
const outputFile = process.argv[4];

if (!zeronetAddress || !outputFolder || !outputFile) {
  console.error('Error: Faltan parámetros. Uso: node extract-events.js <zeronet-address> <output-folder> <output-file>');
  process.exit(1);
}

const folderPath = path.join(__dirname, '..', outputFolder);
const filePath = path.join(folderPath, outputFile);

console.log('Parámetros recibidos:');
console.log(`- Dirección ZeroNet: ${zeronetAddress}`);
console.log(`- Carpeta de destino: ${folderPath}`);
console.log(`- Archivo de salida: ${filePath}`);

(async () => {
  console.log('Iniciando el script...');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  try {
    const zeronetUrl = `http://127.0.0.1:43110/${zeronetAddress}/`;
    console.log(`Extrayendo contenido de: ${zeronetUrl}`);

    // Configuración mejorada para esperar a la carga
    await page.goto(zeronetUrl, {
      waitUntil: 'networkidle',
      timeout: 60000
    });

    console.log('Página cargada, buscando elementos...');

    // Estrategia de espera mejorada
    try {
      // Primero esperamos el contenedor principal
      await page.waitForSelector('.container', { timeout: 30000 });
      console.log('Contenedor principal encontrado');

      // Luego esperamos la tabla o mostramos contenido disponible
      try {
        await page.waitForSelector('#events-table', { timeout: 30000 });
        console.log('Tabla de eventos encontrada');
      } catch (e) {
        console.warn('No se encontró la tabla #events-table, continuando con lo disponible');
      }

      // Esperamos a que haya algún contenido en el cuerpo
      await page.waitForFunction(() => {
        const body = document.querySelector('body');
        return body && body.innerText.trim().length > 100;
      }, { timeout: 30000 });

      // Tomamos captura de pantalla para diagnóstico (opcional)
      await page.screenshot({ path: path.join(folderPath, 'debug.png') });
      console.log('Captura de pantalla guardada para diagnóstico');

      // Extraemos el HTML completo como fallback
      const content = await page.content();
      
      // Crear la carpeta si no existe
      if (!fs.existsSync(folderPath)) {
        fs.mkdirSync(folderPath, { recursive: true });
      }

      // Guardar el contenido
      fs.writeFileSync(filePath, content);
      console.log(`Contenido guardado en: ${filePath}`);

      // Verificar si la tabla está presente en el contenido guardado
      if (content.includes('events-table')) {
        console.log('La tabla de eventos está presente en el archivo guardado');
      } else {
        console.warn('Advertencia: No se detectó la tabla de eventos en el contenido guardado');
        console.warn('El contenido contiene:', content.substring(0, 500) + '...');
      }

    } catch (error) {
      console.error('Error durante la extracción:', error);
      // Guardar el contenido de todos modos para diagnóstico
      const fallbackContent = await page.content();
      fs.writeFileSync(filePath, fallbackContent);
      console.log('Se guardó contenido de fallback para diagnóstico');
      throw error;
    }

  } finally {
    await browser.close();
    console.log('Navegador cerrado');
  }
})();
