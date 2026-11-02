#!/usr/bin/env python3
"""
Abre la web, configura la URL del JSON de AceStream, recarga y
extrae las tablas de eventos (incluida la columna "Eventos Acestream")
a un fichero JSON.
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
ACESTREAM_COLUMN = "Eventos Acestream"
WAIT_FILL_SECONDS = int(os.getenv("WAIT_FILL_SECONDS", "90"))

# JS que recorre todas las tablas de la página y devuelve su contenido.
EXTRACT_JS = """
() => {
  const clean = s => (s || "").replace(/\\s+/g, " ").trim();

  // Busca el título (día) más cercano por encima de la tabla
  const findTitle = table => {
    const cap = table.querySelector("caption");
    if (cap && clean(cap.textContent)) return clean(cap.textContent);
    let el = table;
    while (el) {
      let prev = el.previousElementSibling;
      while (prev) {
        if (/^H[1-6]$/.test(prev.tagName)) return clean(prev.textContent);
        const h = prev.querySelector && prev.querySelector("h1,h2,h3,h4,h5,h6");
        if (h) return clean(h.textContent);
        prev = prev.previousElementSibling;
      }
      el = el.parentElement;
    }
    return "";
  };

  return [...document.querySelectorAll("table")].map(table => {
    let headerCells = [...table.querySelectorAll("thead th")];
    if (!headerCells.length) {
      const firstRow = table.querySelector("tr");
      headerCells = firstRow ? [...firstRow.querySelectorAll("th,td")] : [];
    }
    const headers = headerCells.map(c => clean(c.textContent));

    let bodyRows = [...table.querySelectorAll("tbody tr")];
    if (!bodyRows.length) bodyRows = [...table.querySelectorAll("tr")].slice(1);

    const rows = bodyRows.map(tr => {
      const cells = [...tr.querySelectorAll("td,th")];
      const row = {};
      const links = {};
      cells.forEach((c, i) => {
        const key = headers[i] || ("col_" + i);
        row[key] = clean(c.innerText);
        const found = [...c.querySelectorAll("a[href]")].map(a => ({
          text: clean(a.textContent),
          href: a.getAttribute("href"),
        }));
        // También botones/elementos con data-* o onclick que contengan acestream
        c.querySelectorAll("[data-url],[data-href],[data-hash],[onclick]").forEach(e => {
          const v = e.dataset.url || e.dataset.href || e.dataset.hash || e.getAttribute("onclick");
          if (v) found.push({ text: clean(e.textContent), href: v });
        });
        if (found.length) links[key] = found;
      });
      if (Object.keys(links).length) row["_links"] = links;
      return row;
    });

    return { titulo: findTitle(table), columnas: headers, filas: rows };
  });
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


def acestream_filled(tables):
    """True si alguna celda de la columna Acestream tiene contenido."""
    for t in tables:
        for fila in t["filas"]:
            if fila.get(ACESTREAM_COLUMN) or fila.get("_links", {}).get(ACESTREAM_COLUMN):
                return True
    return False


def click_by_text(page, text, timeout=15000):
    """Pulsa un elemento por su texto: botón, enlace o cualquier elemento."""
    candidates = [
        page.get_by_role("button", name=text),
        page.get_by_role("link", name=text),
        page.locator(f"button:has-text('{text}')"),
        page.get_by_text(text, exact=False),
    ]
    last_err = None
    for loc in candidates:
        try:
            loc.first.wait_for(state="visible", timeout=timeout // len(candidates))
            loc.first.click()
            return loc.first
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"No se pudo pulsar '{text}': {last_err}")


def find_textarea(page):
    """Localiza el cuadro de texto de URLs con varios intentos."""
    candidates = [
        page.get_by_label("URLs de fuentes de AceStream", exact=False),
        page.locator("textarea:visible"),
        page.locator("input[type=text]:visible"),
    ]
    for loc in candidates:
        try:
            loc.first.wait_for(state="visible", timeout=5000)
            return loc.first
        except PWTimeout:
            continue
    raise RuntimeError("No se encontró el cuadro de texto de URLs de AceStream")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="es-ES",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        log(f"Abriendo {SITE_URL}")
        page.goto(SITE_URL, wait_until="networkidle", timeout=60000)
        save_debug(page, "01_inicial")

        log("Pulsando 'Configurar URLs de AceStream'")
        click_by_text(page, "Configurar URLs de AceStream")

        textarea = find_textarea(page)
        textarea.fill(ACESTREAM_JSON_URL)
        save_debug(page, "02_url_pegada")

        log("Pulsando 'Guardar y recargar'")
        try:
            with page.expect_navigation(wait_until="load", timeout=30000):
                click_by_text(page, "Guardar y recargar")
        except PWTimeout:
            # Si la recarga se hizo antes de enganchar el listener, seguimos igualmente
            log("No se detectó navegación explícita; se continúa")
        page.wait_for_load_state("networkidle", timeout=60000)

        log(f"Esperando a que se rellene '{ACESTREAM_COLUMN}' (máx {WAIT_FILL_SECONDS}s)")
        tables = []
        deadline = time.time() + WAIT_FILL_SECONDS
        while time.time() < deadline:
            tables = page.evaluate(EXTRACT_JS)
            if tables and acestream_filled(tables):
                break
            time.sleep(2)
        else:
            log("AVISO: la columna Acestream sigue vacía tras la espera")

        save_debug(page, "03_final")
        try:
            storage = page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
            with open(os.path.join(DEBUG_DIR, "localStorage.json"), "w", encoding="utf-8") as f:
                json.dump(storage, f, ensure_ascii=False, indent=2)
        except Exception as e:  # noqa: BLE001
            log(f"No se pudo leer localStorage: {e}")

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
        browser.close()

        if not tables or not acestream_filled(tables):
            sys.exit(1)


if __name__ == "__main__":
    main()
