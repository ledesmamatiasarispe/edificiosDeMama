"""Versión de la app y de dónde se bajan las actualizaciones.

VERSION se sube a mano antes de publicar una versión nueva, y el tag del release de GitHub tiene que ser "v" + VERSION
(herramientas/empaquetar.py lo controla). REPO es "usuario/repositorio" en GitHub. EDIF_REPO lo reemplaza (para probar
con otro repositorio); vacío desactiva la búsqueda de actualizaciones (así corren los tests)."""
import os

VERSION = "1.0.0"
REPO = os.environ.get("EDIF_REPO", "ledesmamatiasarispe/edificiosDeMama")
