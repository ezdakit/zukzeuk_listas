const { chromium } = require('playwright');
const fs = require('fs');
const { URL } = require('url');

async function captureLoadingContent(zeroNetAddress, baseFilename) {
    const browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();
    
    try {
        // Construct the full ZeroNet URL
        const targetUrl = `http://127.0.0.1:43110/${zeroNetAddress}?accept=1`;
        
        // Start navigation without waiting for completion
        const navigationPromise = page.goto(targetUrl, {
            waitUntil: 'commit',
            timeout: 60000
        });

        // Capture loop while page loads
        for (let i = 0; i < 10; i++) {
            const rawContent = await page.content();
            fs.writeFileSync(
                `${baseFilename}_${i}.html`,
                `<!-- Capture ${i} at ${new Date().toISOString()} -->\n${rawContent}`
            );
            
            // Wait exactly 1 second between captures
            await new Promise(resolve => setTimeout(resolve, 1000));
        }

        // Wait for navigation to complete or timeout
        await navigationPromise.catch(() => {});

    } finally {
        await browser.close();
    }
}

// Execution with CLI parameters
const [,, zeroNetAddress, filename] = process.argv;
if (!zeroNetAddress || !filename) {
    console.error('Usage: node loader.js <zeronet-address> <filename-base>');
    process.exit(1);
}

captureLoadingContent(zeroNetAddress, filename).catch(console.error);
