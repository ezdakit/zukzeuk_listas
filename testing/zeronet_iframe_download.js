const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function captureIframeContent(zeroNetAddress, baseFilename) {
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

        // Locate the iframe
        const iframe = await page.locator('iframe#inner-iframe');

        // Capture content every second for 10 seconds
        for (let i = 0; i < 10; i++) {
            // Wait a second
            await new Promise(resolve => setTimeout(resolve, 1000));

            try {
                // Get the iframe content frame
                const frame = await iframe.contentFrame();

                if (frame) {
                    // Capture iframe content
                    const frameContent = await frame.content(); // This should work correctly
                    const filePath = path.join(outputDir, `${baseFilename}_${i}.html`);
                    fs.writeFileSync(
                        filePath,
                        `<!-- Capture ${i} at ${new Date().toISOString()} -->\n${frameContent}`
                    );
                    console.log(`Captured ${filePath}`);
                } else {
                    console.log('Iframe content not available.');
                }

            } catch (e) {
                console.error(`Failed to capture iframe content for ${baseFilename}_${i}.html: ${e}`);
            }
        }

    } catch (error) {
        console.error(`An error occurred: ${error}`);
    } finally {
        await browser.close();
    }
}

// CLI execution
const [,, zeroNetAddress, filename] = process.argv;
if (!zeroNetAddress || !filename) {
    console.error('Usage: node loader.js <zeronet-address> <filename-base>');
    process.exit(1);
}

captureIframeContent(zeroNetAddress, filename).catch(console.error);
