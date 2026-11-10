"""Arma el paquete que se sube al release de GitHub y que baja el actualizador de la app:
dist/edificiosDeMama-v<VERSION>.zip (el programa, SIN data/ ni .venv/) y su .sha256 (sin él no se instala).

    .venv/bin/python herramientas/empaquetar.py                 (local)
    python herramientas/empaquetar.py --tag v1.2.0              (en GitHub Actions: exige que el tag sea la versión)

Para publicar una versión: subir VERSION en app/version.py, commitear, y crear y empujar el tag "v" + VERSION;
el workflow .github/workflows/release.yml corre los tests, arma el paquete y publica el release."""
import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from app.actualizador import PARTES  # noqa: E402
from app.version import VERSION  # noqa: E402

NOMBRE = "edificiosDeMama"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", help="tag del release (v + VERSION); si no coincide, no se arma")
    tag = p.parse_args().tag
    if tag and tag != "v" + VERSION:
        sys.exit(f"El tag {tag} no coincide con la versión de app/version.py ({VERSION}): subí VERSION antes de etiquetar.")
    dist = RAIZ / "dist"
    dist.mkdir(exist_ok=True)
    paquete = dist / f"{NOMBRE}-v{VERSION}.zip"
    with zipfile.ZipFile(paquete, "w", zipfile.ZIP_DEFLATED) as z:
        for parte in PARTES:
            origen = RAIZ / parte
            archivos = sorted(origen.rglob("*")) if origen.is_dir() else [origen] if origen.exists() else []
            for f in archivos:
                if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                    z.write(f, Path(NOMBRE) / f.relative_to(RAIZ))
    digest = hashlib.sha256(paquete.read_bytes()).hexdigest()
    (dist / (paquete.name + ".sha256")).write_text(f"{digest}  {paquete.name}\n", encoding="ascii")
    print(f"Listo: {paquete} ({paquete.stat().st_size // 1024} KB)\nSHA-256: {digest}")


if __name__ == "__main__":
    main()
