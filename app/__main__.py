"""python -m app  ->  levanta la app en http://localhost:8095

EDIF_PUERTO cambia el puerto y EDIF_DB el archivo de la base (por defecto data/edificios.db)."""
import os

import uvicorn

from app.main import app

PUERTO = int(os.environ.get("EDIF_PUERTO", "8095"))

if __name__ == "__main__":
    print(f"Edificios de Mamá - http://localhost:{PUERTO}  (cerrar esta ventana apaga la app)")
    uvicorn.run(app, host="0.0.0.0", port=PUERTO)
