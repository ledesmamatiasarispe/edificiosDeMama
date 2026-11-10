"""Actualización automática desde los releases de GitHub.

Al arrancar, la app consulta el último release de REPO (app/version.py). Si es más nuevo que la versión instalada, a
los administradores se les pregunta al entrar si quieren actualizar. "Ahora no" no vuelve a preguntar por una semana
(la fecha se guarda en la tabla config: vale para todos, porque la app es una sola).

Instalar:
1. Baja el .zip del release y controla su SHA-256 contra el .sha256 publicado al lado (sin ese archivo no se instala).
2. Lo descomprime en data/actualizacion/ controlando que ningún archivo se escriba fuera de esa carpeta.
3. Hace una copia de la base: data/edificios_antes_de_v<versión>.db.
4. Reemplaza el programa (app/, frontend/ y archivos sueltos de PARTES) sin tocar data/ ni .venv/. Lo anterior queda en
   data/actualizacion/anterior/ hasta la próxima actualización; si algo falla a mitad de camino, se vuelve a poner.
5. Si cambiaron las dependencias (requirements.txt), las instala en el mismo entorno.
6. La app se reinicia sola con la versión nueva (mismo proceso, mismo puerto).

Si la carpeta es un repositorio git con cambios sin guardar en el programa, no se instala (para no pisar trabajo).

Versión COMPILADA (el ejecutable de PyInstaller, sin Python): baja el paquete de su sistema
(edificiosDeMama-vX-windows.zip / -linux.zip / -macos.zip) y reemplaza todo lo que está al lado del ejecutable salvo
data/. En Linux y Mac lo hace la misma app y se reinicia; en Windows (que no deja pisar un programa abierto) deja un
.bat que espera a que la app se cierre, copia los archivos nuevos y la vuelve a abrir.
"""
import hashlib
import json
import os
import shutil
import subprocess
import stat
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

from . import db
from . import version as v
from .validar import ErrorDeNegocio

# EDIF_API_ACTUALIZACION la reemplaza solo para probar contra un servidor local
API = os.environ.get("EDIF_API_ACTUALIZACION", "https://api.github.com/repos/{repo}/releases/latest")
INSTALACION = Path(__file__).resolve().parent.parent
PARTES = ("app", "frontend", "herramientas", "requirements.txt", "requirements-dev.txt", "README.md", "CLAUDE.md",
          "iniciar.py", "iniciar.sh", "iniciar.command", "iniciar.bat", "NOVEDADES.md")
POSPONER_DIAS = 7
_CACHE_SEGUNDOS = 6 * 3600      # la consulta a GitHub se repite cada tanto, no en cada pantalla
_REINTENTO_SEGUNDOS = 10 * 60   # si falló, se vuelve a probar a los 10 minutos

_estado: dict = {}
_lock = threading.Lock()


def _numeros(etiqueta: str) -> tuple:
    """'v1.10.2' -> (1, 10, 2). Lo que no es número (un sufijo '-beta') se ignora."""
    partes = []
    for p in str(etiqueta).strip().lstrip("vV").split("."):
        num = "".join(ch for ch in p.split("-")[0] if ch.isdigit())
        partes.append(int(num) if num else 0)
    return tuple(partes)


def es_mas_nueva(etiqueta: str, actual: str | None = None) -> bool:
    return _numeros(etiqueta) > _numeros(actual or v.VERSION)


def _pedir(url: str, timeout: float = 10) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "EdificiosDeMama/" + v.VERSION, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 (siempre https de GitHub)
        return r.read()


def _config(clave: str) -> str | None:
    with db.transaccion() as c:
        fila = c.execute("SELECT valor FROM config WHERE clave=?", (clave,)).fetchone()
        return fila[0] if fila else None


def _explicar_http(e: urllib.error.HTTPError) -> str:
    cabeceras = e.headers or {}
    if e.code in (403, 429) and cabeceras.get("X-RateLimit-Remaining") == "0":
        return "GitHub limitó por un rato las consultas desde esta red (hasta 60 por hora). La app vuelve a intentar sola."
    return f"No se pudo consultar GitHub (HTTP {e.code})."


def paquete_para(nombres: list[str], compilada: bool | None = None) -> str | None:
    """El .zip que corresponde a esta instalación: el de su sistema si es compilada; el del código fuente si no."""
    compilada = v.COMPILADA if compilada is None else compilada
    zips = [n for n in nombres if n.lower().endswith(".zip")]
    sufijos = tuple(f"-{p}.zip" for p in ("windows", "linux", "macos"))
    if compilada:
        return next((n for n in zips if n.lower().endswith(f"-{v.plataforma()}.zip")), None)
    return next((n for n in zips if not n.lower().endswith(sufijos)), None)


def buscar(forzar: bool = False) -> dict:
    """El último release: versión, notas y el .zip a instalar. Guarda el resultado un rato para no consultar de más."""
    with _lock:
        vigencia = _CACHE_SEGUNDOS if _estado and not _estado["error"] else _REINTENTO_SEGUNDOS
        if not forzar and _estado and time.time() - _estado["buscado"] < vigencia:
            return dict(_estado)
        info = {"buscado": time.time(), "buscado_en": time.strftime("%Y-%m-%d %H:%M"), "error": None,
                "nueva": None, "notas": "", "url_release": None, "zip": None, "sha256": None}
        if not v.REPO:
            info["error"] = "No hay un repositorio de actualizaciones configurado."
        else:
            try:
                rel = json.loads(_pedir(API.format(repo=v.REPO)))
                assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
                info.update(nueva=rel.get("tag_name"), notas=(rel.get("body") or "")[:4000], url_release=rel.get("html_url"))
                nombre = paquete_para(list(assets))
                if nombre:
                    info["zip"] = {"nombre": nombre, "url": assets[nombre]}
                    info["sha256"] = assets.get(nombre + ".sha256")
            except urllib.error.HTTPError as e:
                # 404: el repositorio todavía no publicó ninguna versión (no es una falla)
                info["error"] = None if e.code == 404 else _explicar_http(e)
            except Exception as e:   # sin internet, repositorio mal escrito: no es un error de la app
                info["error"] = f"No se pudo consultar GitHub ({type(e).__name__}: {e})."
        _estado.clear()
        _estado.update(info)
        return dict(info)


def estado(es_admin: bool) -> dict:
    """Lo que necesita la pantalla: si hay versión nueva, y si corresponde preguntarle a este usuario ahora."""
    info = buscar()
    disponible = bool(info["nueva"] and es_mas_nueva(info["nueva"]))
    hasta = _config("actualizacion_pospuesta_hasta")
    pospuesta = bool(hasta and hasta > date.today().isoformat())
    return {"version": v.VERSION, "repo": v.REPO, "disponible": disponible, "nueva": info["nueva"], "notas": info["notas"],
            "url_release": info["url_release"], "instalable": disponible and bool(info["zip"] and info["sha256"]),
            "error": info["error"], "buscado_en": info["buscado_en"], "pospuesta_hasta": hasta if pospuesta else None,
            "preguntar": es_admin and disponible and not pospuesta}


def posponer() -> str:
    """'Ahora no': no se vuelve a preguntar hasta dentro de una semana."""
    hasta = (date.today() + timedelta(days=POSPONER_DIAS)).isoformat()
    with db.transaccion() as c:
        c.execute("INSERT INTO config (clave, valor) VALUES ('actualizacion_pospuesta_hasta', ?) "
                  "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (hasta,))
    return hasta


def _marcador() -> str:
    """El archivo que tiene que traer el paquete para ser la versión correcta de esta instalación."""
    return v.EJECUTABLE if v.COMPILADA else "app/main.py"


def _extraer(zip_path: Path, destino: Path, marcador: str | None = None) -> Path:
    """Descomprime controlando que nada se escriba fuera de `destino` y conservando los permisos de ejecución
    (zipfile no los restaura solo). Devuelve la carpeta que tiene el marcador (app/main.py o el ejecutable)."""
    marcador = marcador or _marcador()
    with zipfile.ZipFile(zip_path) as z:
        base = destino.resolve()
        for nombre in z.namelist():
            if not (base / nombre).resolve().is_relative_to(base):
                raise ErrorDeNegocio("El archivo de la actualización tiene rutas inválidas: no se instala.")
        for info in z.infolist():
            ruta = Path(z.extract(info, destino))
            modo = (info.external_attr >> 16) & 0o777
            if modo and not info.is_dir():
                ruta.chmod(modo | stat.S_IRUSR | stat.S_IWUSR)
    for m in [destino / marcador, *destino.glob("*/" + marcador)]:
        if m.is_file():
            return m.parents[marcador.count("/")]   # la carpeta que contiene el marcador
    raise ErrorDeNegocio(f"La actualización no trae el programa ({marcador}): no se instala.")


def preparar(info: dict, carpeta: Path) -> Path:
    """Baja el .zip, controla el SHA-256 y lo descomprime. Devuelve la carpeta con la versión nueva."""
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir(parents=True)
    datos = _pedir(info["zip"]["url"], timeout=300)
    esperado = _pedir(info["sha256"]).decode("ascii", "replace").split()[0].strip().lower()
    if hashlib.sha256(datos).hexdigest() != esperado:
        raise ErrorDeNegocio("La descarga no coincide con su SHA-256 (archivo dañado o alterado): no se instala.")
    zip_path = carpeta / info["zip"]["nombre"]
    zip_path.write_bytes(datos)
    return _extraer(zip_path, carpeta / "nueva")


def _cambios_sin_guardar(instalacion: Path) -> bool:
    if not (instalacion / ".git").exists():
        return False
    try:
        r = subprocess.run(["git", "status", "--porcelain", "--", "app", "frontend"], cwd=instalacion,
                           capture_output=True, text=True, timeout=30)
        return bool(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def copiar_version(nueva: Path, instalacion: Path, respaldo: Path, partes=PARTES) -> bool:
    """Reemplaza las `partes` de la instalación por las de `nueva` (None = todo lo que trae `nueva`, salvo data/);
    lo anterior queda en `respaldo`. Si algo falla, deja todo como estaba.
    Devuelve True si cambiaron las dependencias (requirements.txt)."""
    if partes is None:
        partes = tuple(p.name for p in nueva.iterdir() if p.name != "data")
    shutil.rmtree(respaldo, ignore_errors=True)
    respaldo.mkdir(parents=True)
    req_antes = (instalacion / "requirements.txt").read_bytes() if (instalacion / "requirements.txt").exists() else b""
    movidas = []
    try:
        for parte in partes:
            origen = nueva / parte
            if not origen.exists():
                continue
            destino = instalacion / parte
            if destino.exists():
                shutil.move(str(destino), str(respaldo / parte))
                movidas.append(parte)
            if origen.is_dir():
                shutil.copytree(origen, destino, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(origen, destino)
                if parte.endswith((".sh", ".command")) or parte == v.EJECUTABLE:
                    destino.chmod(0o755)
    except Exception:
        for parte in partes:   # vuelve a poner lo anterior
            destino = instalacion / parte
            if parte in movidas:
                shutil.rmtree(destino, ignore_errors=True) if destino.is_dir() else destino.unlink(missing_ok=True)
                shutil.move(str(respaldo / parte), str(destino))
        raise
    req_ahora = (instalacion / "requirements.txt").read_bytes() if (instalacion / "requirements.txt").exists() else b""
    return req_antes != req_ahora


def _reiniciar() -> None:
    """Vuelve a arrancar la app en el mismo proceso (mismo PID y puerto) con el programa nuevo."""
    os.environ["EDIF_NAVEGADOR"] = "0"   # el navegador ya está abierto: la página se recarga sola
    if v.COMPILADA:
        exe = Path(sys.executable).resolve().parent / v.EJECUTABLE
        os.execv(str(exe), [str(exe)])
    os.chdir(INSTALACION)
    os.execv(sys.executable, [sys.executable, "-m", "app"])


def _instalar_windows(nueva: Path, instalacion: Path, trabajo: Path, nombre_version: str) -> None:
    """Windows no deja reemplazar un programa abierto: un .bat espera a que la app se cierre, copia y la vuelve a abrir."""
    log = trabajo.parent / "actualizacion.log"
    bat = Path(tempfile.gettempdir()) / f"actualizar_edificios_{os.getpid()}.bat"
    datos = (instalacion / "data").resolve()
    # robocopy sin /MIR: agrega y pisa, nunca borra (así data/ queda como está)
    bat.write_text(f"""@echo off
chcp 65001 >nul
echo Actualizando Edificios de Mamá a {nombre_version}...
:esperar
tasklist /FI "PID eq {os.getpid()}" 2>nul | find "{os.getpid()}" >nul && (timeout /t 1 /nobreak >nul & goto esperar)
robocopy "{nueva}" "{instalacion}" /E /XD "{datos}" /R:10 /W:2 /NP /LOG:"{log}"
set EDIF_NAVEGADOR=0
start "" "{instalacion / v.EJECUTABLE}"
del "%~f0"
""", encoding="utf-8")
    subprocess.Popen(["cmd", "/c", str(bat)], close_fds=True,
                     creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP)
    threading.Timer(1.5, os._exit, [0]).start()   # deja salir la respuesta antes de cerrarse


def instalar(instalacion: Path | None = None, reiniciar=None) -> dict:
    instalacion = instalacion or (Path(sys.executable).resolve().parent if v.COMPILADA else INSTALACION)
    info = buscar(forzar=True)
    if not (info["nueva"] and es_mas_nueva(info["nueva"])):
        raise ErrorDeNegocio("No hay una versión más nueva para instalar.")
    if not (info["zip"] and info["sha256"]):
        raise ErrorDeNegocio("El release no trae el .zip y su .sha256: no se puede instalar automáticamente.")
    if _cambios_sin_guardar(instalacion):
        raise ErrorDeNegocio("Esta copia tiene cambios del programa sin guardar en git: no se actualiza para no pisarlos.")
    trabajo = db.DB_PATH.parent / "actualizacion"
    nueva = preparar(info, trabajo)
    if db.DB_PATH.exists():   # copia de la base antes de cambiar el programa
        copia = db.DB_PATH.parent / f"edificios_antes_de_{info['nueva']}.db"
        copia.unlink(missing_ok=True)
        with db.transaccion() as c:
            c.execute("VACUUM INTO ?", (str(db.DB_PATH.parent / f"edificios_antes_de_{info['nueva']}.db"),))
    if v.COMPILADA and os.name == "nt":
        _instalar_windows(nueva, instalacion, trabajo, info["nueva"])
        return {"ok": True, "nueva": info["nueva"]}
    cambiaron_dependencias = copiar_version(nueva, instalacion, trabajo / "anterior", None if v.COMPILADA else PARTES)
    if cambiaron_dependencias and not v.COMPILADA:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(instalacion / "requirements.txt")],
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            raise ErrorDeNegocio("Se copió la versión nueva pero no se pudieron instalar sus dependencias: "
                                 + (r.stderr or r.stdout)[-400:])
    threading.Timer(1.5, reiniciar or _reiniciar).start()   # deja salir la respuesta antes de reiniciarse
    return {"ok": True, "nueva": info["nueva"]}


def buscar_en_segundo_plano() -> None:
    """Al arrancar: consulta GitHub sin demorar el inicio (la respuesta queda guardada para cuando entre alguien)."""
    if v.REPO:
        threading.Thread(target=buscar, daemon=True).start()
