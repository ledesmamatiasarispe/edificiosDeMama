"""Compila la app para el sistema donde se corre (Windows, Linux o Mac): el programa listo para usar, sin instalar Python.

Deja dist/EdificiosDeMama/ (el ejecutable y _internal/) y el paquete que se sube al release de GitHub:
dist/edificiosDeMama-v<VERSION>-<windows|linux|macos>.zip con su .sha256 (el actualizador no instala sin él).

    .venv/bin/python herramientas/compilar.py                 (local; hace falta: pip install pyinstaller)
    python herramientas/compilar.py --tag v1.2.0              (en GitHub Actions: exige que el tag sea la versión)

La carpeta data/ nunca va en el paquete: es de cada instalación (se crea sola al lado del ejecutable)."""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from app.version import VERSION, plataforma  # noqa: E402

NOMBRE = "EdificiosDeMama"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", help="tag del release (v + VERSION); si no coincide, no se compila")
    tag = p.parse_args().tag
    if tag and tag != "v" + VERSION:
        sys.exit(f"El tag {tag} no coincide con la versión de app/version.py ({VERSION}): subí VERSION antes de etiquetar.")
    dist, build = RAIZ / "dist", RAIZ / "build"
    shutil.rmtree(dist / NOMBRE, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console",
                    "--name", NOMBRE, "--distpath", str(dist), "--workpath", str(build), "--specpath", str(build),
                    "--add-data", f"{RAIZ / 'frontend'}{os.pathsep}frontend",
                    "--collect-submodules", "uvicorn", "--collect-submodules", "app",
                    "--exclude-module", "pytest", str(RAIZ / "app" / "__main__.py")], check=True, cwd=RAIZ)
    for extra in ("README.md", "NOVEDADES.md"):
        shutil.copy2(RAIZ / extra, dist / NOMBRE / extra)
    paquete = dist / f"edificiosDeMama-v{VERSION}-{plataforma()}.zip"
    with zipfile.ZipFile(paquete, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted((dist / NOMBRE).rglob("*")):
            if f.is_file():   # zipfile guarda los permisos (el ejecutable sigue siendo ejecutable al descomprimir)
                z.write(f, Path(NOMBRE) / f.relative_to(dist / NOMBRE))
    digest = hashlib.sha256(paquete.read_bytes()).hexdigest()
    (dist / (paquete.name + ".sha256")).write_text(f"{digest}  {paquete.name}\n", encoding="ascii")
    print(f"Listo: {paquete} ({paquete.stat().st_size // (1024 * 1024)} MB)\nSHA-256: {digest}")


if __name__ == "__main__":
    main()
