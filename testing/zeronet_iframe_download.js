const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function captureIframeContent(zeroNetAddress, baseFilename, captureMultiplier) {
    const browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();

    const outputDir = 'testing';

    try {
        // Limpiar archivos .html existentes en el directorio de salida
        if (fs.existsSync(outputDir)) {
            fs.readdirSync(outputDir).forEach(file => {
                if (file.endsWith('.html')) {
                    fs.unlinkSync(path.join(outputDir, file));
                    console.log(`Eliminado archivo ${file}`);
                }
            });
        } else {
            fs.mkdirSync(outputDir, { recursive: true });
            console.log(`Carpeta ${outputDir} creada.`);
        }

        const targetUrl = `http://127.0.0.1:43110/${zeroNetAddress}?accept=1`;

        // Navigate to the main page
        await page.goto(targetUrl, { waitUntil: 'commit', timeout: 60000 }).catch(e => {
            console.error(`Navigation to ${targetUrl} failed: ${e}`);
        });

        // Wait for iframe to load
        await page.waitForSelector('iframe#inner-iframe');

        // Locate the iframe using frameLocator
        const iframeLocator = page.frameLocator('iframe#inner-iframe');

        // Calculate total seconds to wait and adjust capture interval
        const totalSeconds = captureMultiplier * 10;
        const captureInterval = totalSeconds / 10; // Intervalo en segundos

        // Capture content every interval for the specified total time
        for (let i = 0; i < 10; i++) {
            try {
                // Get the iframe content
                const frameContent = await iframeLocator.locator('body').innerHTML();

                if (!frameContent) {
                    console.log('Iframe content not available.');
                    continue;
                }

                const filePath = path.join(outputDir, `${baseFilename}_${i}.html`);
                fs.writeFileSync(
                    filePath,
                    `<!-- Capture ${i} at ${new Date().toISOString()} -->\n${frame
