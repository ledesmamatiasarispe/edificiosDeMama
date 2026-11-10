"""Versión de la app y de dónde se bajan las actualizaciones.

VERSION se sube a mano antes de publicar una versión nueva, y el tag del release de GitHub tiene que ser "v" + VERSION
(herramientas/empaquetar.py lo controla). REPO es "usuario/repositorio" en GitHub. EDIF_REPO lo reemplaza (para probar
con otro repositorio); vacío desactiva la búsqueda de actualizaciones (así corren los tests)."""
import os
import sys

VERSION = "1.1.0"
REPO = os.environ.get("EDIF_REPO", "ledesmamatiasarispe/edificiosDeMama")

# compilada con PyInstaller (el programa listo para usar, sin Python): se actualiza bajando el paquete de su sistema
COMPILADA = bool(getattr(sys, "frozen", False))
EJECUTABLE = "EdificiosDeMama.exe" if os.name == "nt" else "EdificiosDeMama"


def plataforma() -> str:
    """El sistema en el nombre del paquete compilado: windows, linux o macos."""
    return "windows" if os.name == "nt" else "macos" if sys.platform == "darwin" else "linux"
