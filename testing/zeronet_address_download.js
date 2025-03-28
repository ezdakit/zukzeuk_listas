const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

async function captureLoadingContent(zeroNetAddress, baseFilename) {
    const browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();
    
    // Ruta donde se guardarán los archivos
    const outputDir = 'testing';
    
    try {
        // Verificar si existe la carpeta, si no, crearla
        if (!fs.existsSync(outputDir)) {
            fs.mkdirSync(outputDir, { recursive: true });
            console.log(`Carpeta ${outputDir} creada.`);
        }
        
        // Construir la URL completa
        const targetUrl = `http://127.0.0.1:43110/${zeroNetAddress}?accept=1`;
        
        // Iniciar la navegación sin esperar a que termine
        const navigationPromise = page.goto(targetUrl, {
            waitUntil: 'commit',
            timeout: 60000
        });

        // Capturar contenido cada segundo
        for (let i = 0; i < 10; i++) {
            const rawContent = await page.content();
            const filePath = path.join(outputDir, `${baseFilename}_${i}.html`);
            fs.writeFileSync(
                filePath,
                `<!-- Capture ${i} at ${new Date().toISOString()} -->\n${rawContent}`
            );
            
            // Esperar exactamente 1 segundo entre capturas
            await new Promise(resolve => setTimeout(resolve, 1000));
        }

        // Esperar a que la navegación termine o se agote el tiempo
        await navigationPromise.catch(() => {});

    } finally {
        await browser.close();
    }
}

// Ejecución con parámetros CLI
const [,, zeroNetAddress, filename] = process.argv;
if (!zeroNetAddress || !filename) {
    console.error('Usage: node loader.js <zeronet-address> <filename-base>');
    process.exit(1);
}

captureLoadingContent(zeroNetAddress, filename).catch(console.error);
