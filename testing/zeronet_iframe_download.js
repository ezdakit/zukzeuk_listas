const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function captureIframeContent(zeroNetAddress, baseFilename, captureMultiplier) {
    const browser = await chromium.launch();
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
        
        // Enhanced navigation with multiple wait states
        await page.goto(targetUrl, { 
            waitUntil: 'networkidle',
            timeout: 60000 
        });

        // Robust frame handling with multiple checks
        const getFrameContent = async (attempt = 1) => {
            try {
                // Wait for iframe existence and visibility
                await page.waitForSelector('iframe#inner-iframe', { 
                    state: 'attached',
                    timeout: 10000 
                });
                
                // Multiple methods to access frame
                const frame = await page.$('iframe#inner-iframe')
                    .then(handle => handle.contentFrame())
                    .catch(() => null);

                if (!frame) throw new Error('Frame not found');
                
                // Wait for frame stability
                await frame.waitForLoadState('domcontentloaded');
                await frame.waitForLoadState('networkidle');
                
                // Verify visible content
                const body = await frame.$('body');
                const isVisible = await body.isVisible();
                if (!isVisible) throw new Error('Iframe body not visible');

                return await frame.content();
            } catch (error) {
                if (attempt <= 3) {
                    console.log(`Retry attempt ${attempt}`);
                    await new Promise(resolve => setTimeout(resolve, 2000));
                    return getFrameContent(attempt + 1);
                }
                throw error;
            }
        };

        // Capture logic with retries
        const captureInterval = (captureMultiplier * 10 * 1000) / 10;
        
        for (let i = 0; i < 10; i++) {
            const startTime = Date.now();
            try {
                const content = await getFrameContent();
                const timestamp = new Date().toISOString();
                const filePath = path.join(outputDir, `${baseFilename}_${i}.html`);
                
                fs.writeFileSync(filePath, `<!-- Capture ${i} at ${timestamp} -->\n${content}`);
                console.log(`Success: ${filePath}`);
            } catch (error) {
                console.error(`Capture ${i} failed: ${error.message}`);
            }

            // Precision interval control
            const elapsed = Date.now() - startTime;
            const waitTime = Math.max(0, captureInterval - elapsed);
            await new Promise(resolve => setTimeout(resolve, waitTime));
        }

    } finally {
        await browser.close();
    }
}

// CLI execution
const [,, zeronetAddress, filename, multiplier] = process.argv;
if (!zeronetAddress || !filename || !multiplier) {
    console.error('Usage: node script.js <address> <base-filename> <multiplier>');
    process.exit(1);
}

captureIframeContent(zeronetAddress, filename, parseInt(multiplier));
