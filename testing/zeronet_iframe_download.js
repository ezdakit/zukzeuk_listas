const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function captureIframeContent(zeroNetAddress, baseFilename, captureMultiplier) {
    const browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();

    const outputDir = 'testing';

    try {
        // Clean existing .html files in output directory
        if (fs.existsSync(outputDir)) {
            fs.readdirSync(outputDir).forEach(file => {
                if (file.endsWith('.html')) {
                    fs.unlinkSync(path.join(outputDir, file));
                    console.log(`Deleted file ${file}`);
                }
            });
        } else {
            fs.mkdirSync(outputDir, { recursive: true });
            console.log(`Created folder ${outputDir}.`);
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
        const frame = await iframeLocator.contentFrame();

        // Calculate total seconds to wait and adjust capture interval
        const totalSeconds = captureMultiplier * 10;
        const captureInterval = totalSeconds / 10; // Interval in seconds

        // Capture content every interval for the specified total time
        for (let i = 0; i < 10; i++) {
            try {
                // Wait for a specific element inside the iframe to ensure it's loaded
                await frame?.waitForSelector('body', { timeout: 5000 });

                // Get the iframe content
                const frameContent = await frame?.locator('body').innerHTML();

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
