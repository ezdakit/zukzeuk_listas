const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function captureIframeContent(zeroNetAddress, baseFilename, captureMultiplier) {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    const outputDir = 'testing';

    try {
        // Clean existing files and create directory
        if (fs.existsSync(outputDir)) {
            fs.readdirSync(outputDir).forEach(file => {
                if (file.endsWith('.html')) fs.unlinkSync(path.join(outputDir, file));
            });
        } else {
            fs.mkdirSync(outputDir, { recursive: true });
        }

        const targetUrl = `http://127.0.0.1:43110/${zeroNetAddress}?accept=1`;
        
        let attempts = 0;
        let pageLoaded = false;

        while (!pageLoaded && attempts < 3) {
            try {
                console.log(`Navigating to ${targetUrl} (Attempt ${attempts + 1})`);
                await page.goto(targetUrl, { 
                    waitUntil: 'domcontentloaded',
                    timeout: 30000 // Esperar 30 segundos
                });
                console.log(`Navigation completed`);
                pageLoaded = true;
            } catch (error) {
                console.error(`Failed to load page (Attempt ${attempts + 1}): ${error}`);
                attempts++;
                await new Promise(resolve => setTimeout(resolve, 5000)); // Esperar 5 segundos antes del siguiente intento
            }
        }

        if (!pageLoaded) {
            console.error('Failed to load page after 3 attempts.');
            return;
        }

        // Wait for iframe to load
        await page.waitForSelector('iframe#inner-iframe');

        // Locate the iframe using frameLocator
        const iframeLocator = page.frameLocator('iframe#inner-iframe');

        // Wait for iframe content to load
        await iframeLocator.locator('body').waitFor({ state: 'visible', timeout: 10000 });

        // Calculate total seconds to wait and adjust capture interval
        const totalSeconds = captureMultiplier * 10;
        const captureInterval = totalSeconds / 10; // Interval in seconds

        // Capture content every interval for the specified total time
        for (let i = 0; i < 10; i++) {
            try {
                // Get the iframe content
                const frameContent = await iframeLocator.locator('body').innerHTML();

                if (!frameContent) {
                    console.log('Iframe content not available.');
                    continue;
                }

                const timestamp = new Date().toISOString();
                const filePath = path.join(outputDir, `${baseFilename}_${i}.html`);
                
                fs.writeFileSync(filePath, `<!-- Capture ${i} at ${timestamp} -->\n${frameContent}`);
                console.log(`Captured ${filePath}`);

            } catch (e) {
                console.error(`Failed to capture iframe content for ${baseFilename}_${i}.html: ${e}`);
            }

            // Wait for the capture interval
            if (i < 9) { // No need to wait after last capture
                await new Promise(resolve => setTimeout(resolve, captureInterval * 1000));
            }
        }

    } catch (error) {
        console.error(`An error occurred: ${error}`);
    } finally {
        await browser.close();
    }
}

// CLI execution
const [,, zeroNetAddress, filename, captureMultiplier] = process.argv;
if (!zeroNetAddress || !filename || !captureMultiplier) {
    console.error('Usage: node loader.js <zeronet-address> <filename-base> <capture-multiplier>');
    process.exit(1);
}

captureIframeContent(zeroNetAddress, filename, parseInt(captureMultiplier)).catch(console.error);
