const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function captureIframeContent(zeroNetAddress, baseFilename, captureIntervalMultiplier) {
    const browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();

    const outputDir = 'testing';

    try {
        if (!fs.existsSync(outputDir)) {
            fs.mkdirSync(outputDir, { recursive: true });
            console.log(`Carpeta ${outputDir} creada.`);
        }

        const targetUrl = `http://127.0.0.1:43110/${zeroNetAddress}?accept=1`;

        // Navigate to the main page
        await page.goto(targetUrl, { waitUntil: 'commit', timeout: 60000 }).catch(e => {
            console.error(`Navigation to ${targetUrl} failed: ${e}`);
        });

        // Locate the iframe using frameLocator
        const iframeLocator = page.frameLocator('iframe#inner-iframe');

        // Calculate total seconds to wait and adjust capture interval
        const totalSeconds = captureIntervalMultiplier * 10;
        const captureInterval = 1000; // 1 second

        // Capture content every second for the specified total time
        for (let i = 0; i < totalSeconds; i++) {
            try {
                // Get the iframe content
                const frameContent = await iframeLocator.locator('body').innerHTML();

                const filePath = path.join(outputDir, `${baseFilename}_${i}.html`);
                fs.writeFileSync(
                    filePath,
                    `<!-- Capture ${i} at ${new Date().toISOString()} -->\n${frameContent}`
                );
                console.log(`Captured ${filePath}`);

            } catch (e) {
                console.error(`Failed to capture iframe content for ${baseFilename}_${i}.html: ${e}`);
            }

            // Wait for the capture interval
            await new Promise(resolve => setTimeout(resolve, captureInterval));
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
