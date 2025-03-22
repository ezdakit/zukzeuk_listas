(async () => {
  console.log('Iniciando el script...');

  // Verificar si ZeroNet está funcionando
  if (!(await isZeroNetRunning())) {
    console.error('Error: ZeroNet no está funcionando. Saliendo...');
    process.exit(1);
  }

  // Lanzar el navegador Chromium
  console.log('Lanzando el navegador Chromium...');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  console.log('Navegador lanzado correctamente.');

  // Extraer contenido dinámico de la primera página (eventos.html)
  const zeronetUrl1 = `http://127.0.0.1:43110/${zeronetAddress1}/`;
  console.log(`Extrayendo contenido de: ${zeronetUrl1}`);

  try {
    // Configurar el encabezado "Accept" para páginas HTML
    console.log('Configurando encabezado "Accept: text/html"...');
    await page.setExtraHTTPHeaders({
      'Accept': 'text/html',
    });

    // Cargar la página con reintentos
    await loadPageWithRetries(page, zeronetUrl1);

    // Esperar a que el iframe se cargue
    console.log('Esperando a que el iframe se cargue...');
    await page.waitForSelector('#inner-iframe', { timeout: 10000 }); // Timeout de 10 segundos
    console.log('Iframe cargado correctamente.');

    // Obtener el contenido del iframe
    console.log('Obteniendo el contenido del iframe...');
    const iframeHandle = await page.$('#inner-iframe');
    const frame = await iframeHandle.contentFrame();

    // Esperar a que la tabla "tablaAcestream" esté presente y visible
    console.log('Esperando a que la tabla "tablaAcestream" se cargue...');
    await frame.waitForSelector('#tablaAcestream', { timeout: 10000 }); // Timeout de 10 segundos
    console.log('Tabla "tablaAcestream" cargada correctamente.');

    // Verificar que la tabla esté visible (display: table)
    console.log('Verificando que la tabla esté visible...');
    const isTableVisible = await frame.$eval('#tablaAcestream', (table) => {
      return window.getComputedStyle(table).display === 'table';
    });

    if (!isTableVisible) {
      throw new Error('La tabla "tablaAcestream" no está visible.');
    }
    console.log('La tabla "tablaAcestream" está visible.');

    // Obtener el HTML final del iframe
    console.log('Obteniendo el HTML final del iframe...');
    const finalContent = await frame.content();

    // Crear la carpeta si no existe
    if (!fs.existsSync(folderPath)) {
      console.log(`Creando carpeta: ${folderPath}`);
      fs.mkdirSync(folderPath, { recursive: true });
    }

    // Guardar el contenido en un archivo
    console.log(`Guardando contenido en: ${filePath}`);
    fs.writeFileSync(filePath, finalContent);
    console.log(`Archivo guardado correctamente: ${filePath}`);
  } catch (error) {
    console.error(`Error al extraer el contenido: ${error.message}`);
    process.exit(1); // Terminar el script con un código de error
  }

  // Cerrar el navegador
  console.log('Cerrando el navegador...');
  await browser.close();
  console.log('Navegador cerrado correctamente.');

  console.log('Script completado con éxito.');
})();
