#!/usr/bin/env python3
"""
Andrenalina - 3 Días: configura las URLs de AceStream y descarga las tablas
de eventos (incluida la columna "Eventos Acestream") a un JSON.

Pasos que replica:
  1. Abrir la web (y aceptar el EULA, si ACCEPT_EULA=yes).
  2. Abrir "Configuración" si el panel está cerrado.
  3. Escribir la URL del hashes.json en #urlsInput.
  4. Pulsar #btnSaveUrls ("Guardar y Recargar").
  5. Esperar a que se rellene la columna y extraer las tablas.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

SITE_URL = os.getenv("SITE_URL", "https://kiroideuno.pages.gay")
ACESTREAM_JSON_URL = os.getenv(
    "ACESTREAM_JSON_URL",
    "https://tokyo.elcano-ipfs.workers.dev/"
    "k51qzi5uqu5dh5qej4b9wlcr5i6vhc7rcfkekhrxqek5c9lk6gdaiik820fecs/hashes.json",
)
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "eventos.json")
DEBUG_DIR = os.getenv("DEBUG_DIR", "debug")
WAIT_FILL_SECONDS = int(os.getenv("WAIT_FILL_SECONDS", "90"))
ACCEPT_EULA = os.getenv("ACCEPT_EULA", "no").strip().lower() == "yes"
ACESTREAM_COLUMN = "Eventos Acestream"

TABLE_IDS = ["tablaAyer", "tablaHoy", "tablaManana", "tablaPasado", "tablaAcestream"]

EXTRACT_JS = """
(ids) => {
  const clean = s => (s || "").replace(/\\s+/g, " ").trim();
  const out = [];
  for (const id of ids) {
    const table = document.getElementById(id);
    if (!table) continue;
    const visible = getComputedStyle(table).display !== "none";

    // Título: el <h2 id="titulo..."> correspondiente
    const h2 = document.getElementById("titulo" + id.replace(/^tabla/, ""));
    const titulo = h2 ? clean(h2.textContent) : "";

    const headers = [...table.querySelectorAll("thead th")].map(th => clean(th.textContent));
    const rows = [...table.querySelectorAll("tbody tr")].map(tr => {
      const row = {};
      const links = {};
      [...tr.children].forEach((td, i) => {
        const key = headers[i] || ("col_" + i);
        // innerText respeta los <br> como saltos de línea
        row[key] = (td.innerText || "").split("\\n").map(clean).filter(Boolean).join(" | ");
        const found = [...td.querySelectorAll("a[href]")].map(a => ({
          texto: clean(a.textContent),
          href: a.getAttribute("href"),
        }));
        if (found.length) links[key] = found;
      });
      if (Object.keys(links).length) row["_enlaces"] = links;
      return row;
    });
    out.push({ id, titulo, visible, columnas: headers, filas: rows });
  }
  return out;
}
"""


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def save_debug(page, name):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    try:
        page.screenshot(path=os.path.join(DEBUG_DIR, f"{name}.png"), full_page=True)
        with open(os.path.join(DEBUG_DIR, f"{name}.html"), "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception as e:  # noqa: BLE001
        log(f"No se pudo guardar debug '{name}': {e}")


def handle_eula(page):
    """Si aparece el EULA, lo acepta solo cuando ACCEPT_EULA=yes."""
    page.wait_for_function(
        """() => {
            const o = document.getElementById('eula-overlay');
            const c = document.getElementById('contenido-app');
            const eulaVisible = o && getComputedStyle(o).display !== 'none';
            const appVisible = c && !c.hidden && getComputedStyle(c).display !== 'none';
            return eulaVisible || appVisible;
        }""",
        timeout=30000,
    )
    if not page.locator("#eula-overlay").is_visible():
        log("EULA ya aceptado o no necesario")
        return

    if not ACCEPT_EULA:
        save_debug(page, "eula")
        log(
            "La web muestra un EULA. Lee los términos y, si los aceptas, "
            "define ACCEPT_EULA=yes (en el workflow) para que el script lo acepte."
        )
        sys.exit(2)

    frase = page.locator("#eula-frase-label").inner_text().strip()
    log(f"Aceptando EULA (frase: {frase!r})")
    page.locator("#eula-confirm-input").fill(frase)
    page.locator("#eula-accept-btn").click()
    page.wait_for_function(
        "() => { const c = document.getElementById('contenido-app'); return c && !c.hidden; }",
        timeout=15000,
    )


def acestream_filled(tables):
    """True si alguna celda de la columna Acestream tiene algo más que '-'."""
    for t in tables:
        for fila in t["filas"]:
            valor = fila.get(ACESTREAM_COLUMN, "").strip()
            if valor and valor != "-":
                return True
    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="es-ES",
            timezone_id="Europe/Madrid",
        )
        page = context.new_page()
        try:
            log(f"Abriendo {SITE_URL}")
            page.goto(SITE_URL, wait_until="domcontentloaded", timeout=60000)
            handle_eula(page)
            page.wait_for_load_state("networkidle", timeout=60000)
            save_debug(page, "01_inicial")

            # Abrir el panel de configuración si está cerrado
            if not page.locator("#urlsInput").is_visible():
                log("Abriendo panel de configuración")
                page.locator("#btnToggleConfig").click()
            page.locator("#urlsInput").wait_for(state="visible", timeout=15000)

            log("Escribiendo la URL del JSON de AceStream")
            page.locator("#urlsInput").fill(ACESTREAM_JSON_URL)
            save_debug(page, "02_url_pegada")

            log("Pulsando 'Guardar y Recargar'")
            try:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
                    page.locator("#btnSaveUrls").click()
            except PWTimeout:
                log("No se detectó navegación explícita; se continúa")

            # Tras recargar, el EULA ya está aceptado (cookie), pero por si acaso:
            handle_eula(page)
            page.wait_for_load_state("networkidle", timeout=60000)

            log(f"Esperando a que se rellene '{ACESTREAM_COLUMN}' (máx {WAIT_FILL_SECONDS}s)")
            tables = []
            deadline = time.time() + WAIT_FILL_SECONDS
            while time.time() < deadline:
                tables = page.evaluate(EXTRACT_JS, TABLE_IDS)
                if tables and acestream_filled(tables):
                    # pequeña pausa para que terminen de pintarse todas las tablas
                    time.sleep(3)
                    tables = page.evaluate(EXTRACT_JS, TABLE_IDS)
                    break
                time.sleep(2)
            else:
                log("AVISO: la columna Acestream sigue vacía tras la espera")

            save_debug(page, "03_final")
        except Exception:
            save_debug(page, "error")
            raise
        finally:
            browser.close()

    resultado = {
        "fuente": SITE_URL,
        "acestream_json": ACESTREAM_JSON_URL,
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tablas": tables,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    total = sum(len(t["filas"]) for t in tables)
    log(f"Guardado {OUTPUT_FILE}: {len(tables)} tablas, {total} filas")
    if not acestream_filled(tables):
        sys.exit(1)


if __name__ == "__main__":
    main()
