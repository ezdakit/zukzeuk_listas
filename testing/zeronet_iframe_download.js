// capture_zeronet.js
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// --- Configuration ---
const ZERONET_BASE_URL = 'http://127.0.0.1:43110';
const OUTPUT_DIR = 'testing';
const SNAPSHOT_COUNT = 10;
const IFRAME_SELECTOR = '#inner-iframe'; // Default ZeroNet iframe ID

// --- Helper Functions ---
function printUsage() {
    console.error(`
Usage: node capture_zeronet.js <zeroNetSiteId> <baseFilename> <waitTimeMultiplier>

Arguments:
  <zeroNetSiteId>      : The ZeroNet site ID (e.g., 1HeLLo4uzjaLetFx6NH3PMwFP3qbRbTf3D)
  <baseFilename>       : The base name for the output HTML files (e.g., site_capture)
  <waitTimeMultiplier> : An integer. Total wait time will be multiplier * 10 seconds.
                         Snapshots will be taken every 'multiplier' seconds.

Example:
  node capture_zeronet.js 1HeLLo4uzjaLetFx6NH3PMwFP3qbRbTf3D mypage 3
  (This will wait 30 seconds total, taking 10 snapshots every 3 seconds)
`);
}

async function cleanupOutputDir(dirPath) {
    try {
        if (fs.existsSync(dirPath)) {
            const files = fs.readdirSync(dirPath);
            console.log(`Cleaning up existing .html files in '${dirPath}'...`);
            for (const file of files) {
                if (file.endsWith('.html')) {
                    const filePath = path.join(dirPath, file);
                    try {
                        fs.unlinkSync(filePath);
                        console.log(`  Deleted: ${file}`);
                    } catch (unlinkErr) {
                        console.error(`  Error deleting file ${filePath}:`, unlinkErr.message);
                    }
                }
            }
        } else {
            console.log(`Output directory '${dirPath}' does not exist. It will be created.`);
        }
    } catch (err) {
        console.error(`Error during cleanup of directory ${dirPath}:`, err.message);
        // Decide if you want to exit or continue
        // process.exit(1);
    }
}

async function createOutputDir(dirPath) {
    try {
        if (!fs.existsSync(dirPath)) {
            fs.mkdirSync(dirPath, { recursive: true });
            console.log(`Created output directory: '${dirPath}'`);
        } else {
             console.log(`Output directory '${dirPath}' already exists.`);
        }
    } catch (err) {
        console.error(`Error creating output directory '${dirPath}':`, err.message);
        process.exit(1); // Exit if we can't create the directory
    }
}


// --- Main Script Logic ---
(async () => {
    // 1. Parse Command Line Arguments
    const args = process.argv.slice(2); // Skip 'node' and script name
    if (args.length !== 3) {
        console.error("Error: Incorrect number of arguments.");
        printUsage();
        process.exit(1);
    }

    const zeroNetSiteId = args[0];
    const baseFilename = args[1];
    const waitTimeMultiplier = parseInt(args[2], 10);

    if (isNaN(waitTimeMultiplier) || waitTimeMultiplier <= 0) {
        console.error("Error: <waitTimeMultiplier> must be a positive integer.");
        printUsage();
        process.exit(1);
    }

    const totalWaitSeconds = waitTimeMultiplier * 10;
    const snapshotIntervalSeconds = waitTimeMultiplier; // (totalWaitSeconds / SNAPSHOT_COUNT)
    const snapshotIntervalMs = snapshotIntervalSeconds * 1000;

    console.log(`--- ZeroNet Page Snapshot Script ---`);
    console.log(`Site ID          : ${zeroNetSiteId}`);
    console.log(`Base Filename    : ${baseFilename}`);
    console.log(`Wait Multiplier  : ${waitTimeMultiplier}`);
    console.log(`Total Wait Time  : ${totalWaitSeconds} seconds`);
    console.log(`Snapshot Interval: ${snapshotIntervalSeconds} seconds (${SNAPSHOT_COUNT} snapshots)`);
    console.log(`Output Directory : ${OUTPUT_DIR}`);
    console.log(`------------------------------------`);


    // 2. Prepare Output Directory
    const outputDirPath = path.resolve(OUTPUT_DIR); // Get absolute path
    await cleanupOutputDir(outputDirPath);
    await createOutputDir(outputDirPath);


    // 3. Launch Browser and Navigate
    let browser;
    try {
        console.log("Launching browser...");
        browser = await chromium.launch(); // Or firefox, webkit
        const context = await browser.newContext({
            // Ignore HTTPS errors if ZeroNet uses self-signed certs (less common now)
             ignoreHTTPSErrors: true,
        });
        const page = await context.newPage();

        const initialUrl = `${ZERONET_BASE_URL}/${zeroNetSiteId}/`;
        console.log(`Navigating to ZeroNet wrapper page: ${initialUrl}`);
        // Increase navigation timeout if needed for slow ZeroNet startup/proxy
        await page.goto(initialUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
        console.log("Wrapper page loaded (DOM content). Waiting for iframe...");

        // Wait specifically for the iframe to be present in the DOM
        try {
            await page.waitForSelector(IFRAME_SELECTOR, { timeout: 30000 }); // Wait up to 30s for iframe tag
            console.log("Iframe element found.");
        } catch (error) {
             console.error(`Error: Could not find the iframe ('${IFRAME_SELECTOR}') within 30 seconds.`);
             console.error("Check if the ZeroNet site is loading correctly or if the iframe ID has changed.");
             await browser.close();
             process.exit(1);
        }

        const frame = page.frameLocator(IFRAME_SELECTOR);

        // It might take a moment for the iframe's *content* to start loading,
        // let's add a small initial delay before the first snapshot.
        console.log("Waiting briefly for iframe content to begin loading...");
        await page.waitForTimeout(2000); // 2 seconds initial buffer


        // 4. Capture Snapshots Periodically
        console.log(`Starting snapshot capture every ${snapshotIntervalSeconds} seconds...`);
        for (let i = 0; i < SNAPSHOT_COUNT; i++) {
            try {
                 // Get the HTML content *inside* the iframe
                const iframeContent = await frame.content(); // Gets the full HTML document within the iframe
                const filename = `${baseFilename}_${i}.html`;
                const filePath = path.join(outputDirPath, filename);

                fs.writeFileSync(filePath, iframeContent);
                console.log(`[${new Date().toLocaleTimeString()}] Saved snapshot: ${filename}`);

                // Wait for the next interval, unless it's the last snapshot
                if (i < SNAPSHOT_COUNT - 1) {
                    await page.waitForTimeout(snapshotIntervalMs);
                }
            } catch (error) {
                 console.error(`Error capturing or saving snapshot ${i}:`, error.message);
                 // Optional: Decide whether to continue or stop on error
                 // break;
            }
        }

        console.log("Finished capturing snapshots.");

    } catch (error) {
        console.error("\nAn error occurred during the process:", error);
        process.exitCode = 1; // Indicate failure
    } finally {
        if (browser) {
            console.log("Closing browser...");
            await browser.close();
        }
        console.log("Script finished.");
    }
})();
