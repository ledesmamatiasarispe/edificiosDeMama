"""python -m app (o el ejecutable compilado EdificiosDeMama) -> levanta la app en http://localhost:8095

EDIF_PUERTO cambia el puerto y EDIF_DB el archivo de la base (por defecto data/edificios.db).
La versión compilada además abre el navegador al arrancar (EDIF_NAVEGADOR=0 lo evita), y si la app ya estaba
funcionando en ese puerto, solo abre el navegador."""
import json
import os
import threading
import urllib.request
import webbrowser

import uvicorn

from app.main import app
from app.version import COMPILADA, VERSION

PUERTO = int(os.environ.get("EDIF_PUERTO", "8095"))
URL = f"http://localhost:{PUERTO}"


def _ya_funcionando() -> bool:
    try:
        with urllib.request.urlopen(URL + "/api/version", timeout=2) as r:
            return "version" in json.loads(r.read())
    except Exception:
        return False


if __name__ == "__main__":
    abrir = COMPILADA and os.environ.get("EDIF_NAVEGADOR", "1") != "0"
    if COMPILADA and _ya_funcionando():
        print(f"Edificios de Mamá ya está funcionando: {URL}")
        if abrir:
            webbrowser.open(URL)
    else:
        print(f"Edificios de Mamá {VERSION} - {URL}  (cerrar esta ventana apaga la app)")
        if abrir:
            threading.Timer(2.5, webbrowser.open, [URL]).start()
        # el objeto app directo (no "app.main:app"): compilada, uvicorn no puede importar el módulo por nombre
        uvicorn.run(app, host="0.0.0.0", port=PUERTO)
