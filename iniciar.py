"""Lanzador de Edificios de Mamá, igual para Windows, Linux y Mac.

Se abre con doble clic desde iniciar.bat (Windows), iniciar.command (Mac) o iniciar.sh (Linux), que solo llaman a este archivo.
1. La primera vez crea el entorno de Python (.venv) e instala lo necesario; si cambian las dependencias, las actualiza.
2. Si la app ya está funcionando, solo abre el navegador.
3. Si no, la arranca y abre el navegador cuando está lista. Cerrar la ventana (o Ctrl+C) apaga la app.

    python3 iniciar.py                     arrancar
    python3 iniciar.py --sin-navegador     arrancar sin abrir el navegador
    python3 iniciar.py --acceso-directo    (Linux) agrega "Edificios de Mamá" al menú de aplicaciones y al escritorio
Usa solo la biblioteca estándar: tiene que andar antes de que exista el entorno."""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
VENV = RAIZ / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
MARCA = VENV / "dependencias_instaladas.txt"   # copia del requirements.txt con el que se instaló
PUERTO = int(os.environ.get("EDIF_PUERTO", "8095"))
URL = f"http://localhost:{PUERTO}"
MINIMO = (3, 10)


def avisar_y_salir(texto: str) -> None:
    print("\n" + texto)
    if os.name == "nt":
        input("\nApretá Enter para cerrar esta ventana.")
    sys.exit(1)


def preparar() -> None:
    """Crea el entorno y/o instala las dependencias si hace falta."""
    requisitos = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    if PY.exists() and MARCA.exists() and MARCA.read_text(encoding="utf-8") == requisitos:
        return
    if not PY.exists():
        print("Preparando la app por primera vez (puede tardar un par de minutos)...")
        venv.create(VENV, with_pip=True)
    else:
        print("Actualizando lo que necesita la app...")
    r = subprocess.run([str(PY), "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", str(RAIZ / "requirements.txt")])
    if r.returncode != 0:
        avisar_y_salir("No se pudo instalar lo que necesita la app. Revisá la conexión a internet y probá de nuevo.")
    MARCA.write_text(requisitos, encoding="utf-8")


def funcionando() -> str | None:
    """La versión de la app si ya está funcionando en el puerto; None si no."""
    try:
        with urllib.request.urlopen(URL + "/api/version", timeout=2) as r:
            return json.loads(r.read()).get("version")
    except Exception:
        return None


def abrir_cuando_este_lista() -> None:
    for _ in range(120):
        if funcionando():
            webbrowser.open(URL)
            return
        time.sleep(0.5)


def acceso_directo() -> None:
    """Linux: un ícono en el menú de aplicaciones (y en el escritorio) que abre la app."""
    if not sys.platform.startswith("linux"):
        avisar_y_salir("El acceso directo automático es para Linux. En Windows y Mac: clic derecho sobre iniciar.bat o "
                       "iniciar.command y crear un acceso directo (o alias) en el escritorio.")
    lanzador = RAIZ / "iniciar.sh"
    contenido = f"""[Desktop Entry]
Type=Application
Name=Edificios de Mamá
Comment=Administración de consorcios
Exec="{lanzador}"
Path={RAIZ}
Icon={RAIZ / "frontend" / "icono.svg"}
Terminal=true
Categories=Office;Finance;
"""
    menu = Path.home() / ".local" / "share" / "applications" / "edificios-de-mama.desktop"
    menu.parent.mkdir(parents=True, exist_ok=True)
    destinos = [menu]
    escritorio = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True).stdout.strip() or str(Path.home() / "Desktop")
    if Path(escritorio).is_dir():
        destinos.append(Path(escritorio) / "edificios-de-mama.desktop")
    for d in destinos:
        d.write_text(contenido, encoding="utf-8")
        d.chmod(0o755)
        print("Acceso directo creado:", d)


def main() -> None:
    if sys.version_info < MINIMO:
        avisar_y_salir(f"Hace falta Python {MINIMO[0]}.{MINIMO[1]} o más nuevo (este es {sys.version.split()[0]}). "
                       "Se baja gratis de https://www.python.org/downloads/")
    if "--acceso-directo" in sys.argv:
        return acceso_directo()
    version = funcionando()
    if version:
        print(f"La app ya está funcionando (versión {version}). Abriendo el navegador...")
        if "--sin-navegador" not in sys.argv:
            webbrowser.open(URL)
        return
    preparar()
    print(f"Edificios de Mamá: {URL}  (cerrar esta ventana apaga la app)")
    if "--sin-navegador" not in sys.argv:
        threading.Thread(target=abrir_cuando_este_lista, daemon=True).start()
    try:
        r = subprocess.run([str(PY), "-m", "app"], cwd=RAIZ)
    except KeyboardInterrupt:
        return
    if r.returncode not in (0, None) and r.returncode > 0:
        avisar_y_salir("La app se cerró por un error. El detalle está más arriba en esta ventana.")


if __name__ == "__main__":
    main()
