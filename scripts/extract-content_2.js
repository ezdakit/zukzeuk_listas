const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Configuración mejorada
const DEBUG_MODE = true;
const MAX_RETRIES = 3;
const TIMEOUT = 180000; // Aumentado a 3 minutos
const IFRAME_LOAD_TIMEOUT = 60000; // Tiempo específico para iframe

// Función mejorada para esperar contenido del iframe
async function waitForIframeContent(frame) {
  // Intentar múltiples estrategias de espera
  try {
    // 1. Esperar por networkidle
    await frame.waitForLoadState('networkidle', { timeout: IFRAME_LOAD_TIMEOUT/2 });
    return true;
  } catch (e) {
    console.log('Estrategia networkidle fallida, intentando domcontentloaded...');
    try {
      // 2. Esperar por DOMContentLoaded
      await frame.waitForLoadState('domcontentloaded', { timeout: IFRAME_LOAD_TIMEOUT/2 });
      return true;
    } catch (e) {
      console.log('Estrategia domcontentloaded fallida, intentando por contenido...');
      // 3. Esperar por cualquier contenido
      await frame.waitForFunction(
        () => document.body.innerText.length > 100,
        { timeout: IFRAME_LOAD_TIMEOUT }
      );
      return true;
    }
  }
}

// Función principal mejorada
(async () => {
  let browser;
  let page;
  let frame;
  
  try {
    // [Configuración inicial igual que antes...]
    
    while (attempt < MAX_RETRIES && !success) {
      attempt++;
      console.log(`\n=== INTENTO ${attempt} de ${MAX_RETRIES} ===`);

      try {
        // [Navegación y detección de iframe igual que antes...]
        
        console.log('Esperando contenido del iframe...');
        await waitForIframeContent(frame); // Usamos nuestra nueva función
        
        console.log('Verificando elementos...');
        // Estrategia de espera flexible para la tabla
        const tableFound = await Promise.race([
          frame.waitForSelector('#events-table', { timeout: 30000 }).then(() => true),
          frame.waitForSelector('.table-container', { timeout: 30000 }).then(() => true),
          new Promise(resolve => setTimeout(() => resolve(false), 30000))
        ]);

        if (!tableFound) {
          throw new Error('No se encontraron elementos de la tabla');
        }

        console.log('Extrayendo contenido...');
        const content = await frame.evaluate(() => {
          // Extraer toda la página como fallback
          const tableContainer = document.querySelector('.table-container') || document.body;
          return tableContainer.outerHTML;
        });

        fs.writeFileSync(filePath, content);
        console.log(`✅ Contenido guardado en ${filePath}`);
        success = true;

      } catch (attemptError) {
        console.error(`❌ Error en intento ${attempt}:`, attemptError.message);
        
        // Guardar estado actual del iframe
        if (frame) {
          const iframeState = await frame.evaluate(() => ({
            readyState: document.readyState,
            bodyLength: document.body.innerText.length,
            error: window.document.error
          }));
          console.log('Estado del iframe:', iframeState);
        }

        // [Resto del manejo de errores igual...]
      }
    }
  } catch (finalError) {
    // [Manejo de errores final igual...]
  } finally {
    // [Cierre igual que antes...]
  }
})();
