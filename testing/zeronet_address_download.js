const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function captureLoadingContent(zeroNetAddress, baseFilename) {
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

        // Start navigation
        await page.goto(targetUrl, { waitUntil: 'commit', timeout: 60000 }).catch(e => {
            console.error(`Navigation to ${targetUrl} failed: ${e}`);
        });

        // Capture content every second for 10 seconds
        for (let i = 0; i < 10; i++) {
            // Wait a second before capturing content
            await new Promise(resolve => setTimeout(resolve, 1000));

            try {
                // Capture page content
                const rawContent = await page.content();
                const filePath = path.join(outputDir, `${baseFilename}_${i}.html`);
                fs.writeFileSync(
                    filePath,
                    `<!-- Capture ${i} at ${new Date().toISOString()} -->\n${rawContent}`
                );
                console.log(`Captured ${filePath}`);
            } catch (e) {
                console.error(`Failed to capture content for ${baseFilename}_${i}.html: ${e}`);
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

captureLoadingContent(zeroNetAddress, filename).catch(console.error);
