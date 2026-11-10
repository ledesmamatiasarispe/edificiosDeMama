"""Actualizaciones desde los releases de GitHub (GitHub simulado: nunca se sale a internet en los tests)."""
import hashlib
import io
import json
import zipfile
from datetime import date, timedelta

import pytest

from app import actualizador as act


def zip_con(archivos: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nombre, datos in archivos.items():
            z.writestr(nombre, datos)
    return buf.getvalue()


@pytest.fixture()
def github(monkeypatch):
    """Un release v9.0.0 con su .zip y .sha256. Devuelve el dict de respuestas por URL, para cambiarlas en cada test."""
    paquete = zip_con({"edificiosDeMama/app/main.py": b"# nuevo", "edificiosDeMama/app/__init__.py": b"",
                       "edificiosDeMama/frontend/app.js": b"// nuevo", "edificiosDeMama/requirements.txt": b"fastapi\n"})
    respuestas = {
        act.API.format(repo="prueba/edificios"): json.dumps({
            "tag_name": "v9.0.0", "body": "- Novedad 1", "html_url": "https://github.com/prueba/edificios/releases/v9.0.0",
            "assets": [{"name": "edificiosDeMama-v9.0.0.zip", "browser_download_url": "https://x/zip"},
                       {"name": "edificiosDeMama-v9.0.0.zip.sha256", "browser_download_url": "https://x/sha"}]}).encode(),
        "https://x/zip": paquete,
        "https://x/sha": (hashlib.sha256(paquete).hexdigest() + "  edificiosDeMama-v9.0.0.zip\n").encode(),
    }

    def pedir(url, timeout=10):
        if isinstance(respuestas.get(url), Exception):
            raise respuestas[url]
        return respuestas[url]

    monkeypatch.setattr(act, "_pedir", pedir)
    monkeypatch.setattr(act.v, "REPO", "prueba/edificios")
    act._estado.clear()
    yield respuestas
    act._estado.clear()


def test_comparar_versiones():
    assert act.es_mas_nueva("v1.0.1", "1.0.0") and act.es_mas_nueva("v1.10.0", "1.9.9") and act.es_mas_nueva("2.0", "1.9.9")
    assert not act.es_mas_nueva("v1.0.0", "1.0.0") and not act.es_mas_nueva("v0.9.9", "1.0.0")
    assert not act.es_mas_nueva("v1.0.0-beta", "1.0.0")


def test_sin_repositorio_no_busca(cliente, monkeypatch):
    monkeypatch.setattr(act.v, "REPO", "")
    act._estado.clear()
    a = cliente.get("/api/actualizacion").json()
    assert a["repo"] == "" and not a["disponible"] and not a["preguntar"]


def test_hay_version_nueva_y_se_pregunta_al_admin(cliente, github):
    a = cliente.get("/api/actualizacion").json()
    assert a["disponible"] and a["instalable"] and a["preguntar"] and a["nueva"] == "v9.0.0"


def test_posponer_una_semana(cliente, github):
    r = cliente.post("/api/actualizacion/posponer").json()
    assert r["pospuesta_hasta"] == (date.today() + timedelta(days=7)).isoformat()
    a = cliente.get("/api/actualizacion").json()
    assert a["disponible"] and not a["preguntar"]


def test_sin_releases_no_es_error(cliente, github):
    import urllib.error
    github[act.API.format(repo="prueba/edificios")] = urllib.error.HTTPError("u", 404, "no", {}, None)
    a = cliente.post("/api/actualizacion/buscar").json()
    assert a["error"] is None and not a["disponible"]


def test_sha_que_no_coincide_no_se_instala(cliente, github, tmp_path):
    github["https://x/sha"] = b"0" * 64
    (tmp_path / "instalacion").mkdir()
    with pytest.raises(act.ErrorDeNegocio, match="SHA-256"):
        act.instalar(tmp_path / "instalacion", reiniciar=lambda: None)
    assert not (tmp_path / "instalacion" / "app").exists()


def test_zip_con_rutas_peligrosas_no_se_instala(tmp_path):
    z = tmp_path / "malo.zip"
    z.write_bytes(zip_con({"../afuera.txt": b"x", "app/main.py": b""}))
    with pytest.raises(act.ErrorDeNegocio):
        act._extraer(z, tmp_path / "destino")
    assert not (tmp_path / "afuera.txt").exists()


def test_instalar_reemplaza_el_programa_sin_tocar_los_datos(cliente, github, tmp_path, monkeypatch):
    instalacion = tmp_path / "instalacion"
    (instalacion / "app").mkdir(parents=True)
    (instalacion / "app" / "main.py").write_text("# viejo")
    (instalacion / "app" / "viejo_suelto.py").write_text("# ya no existe en la nueva")
    (instalacion / "frontend").mkdir()
    (instalacion / "frontend" / "app.js").write_text("// viejo")
    (instalacion / "requirements.txt").write_text("fastapi\n")
    (instalacion / "data").mkdir()
    (instalacion / "data" / "mio.txt").write_text("no tocar")
    reinicios = []
    r = act.instalar(instalacion, reiniciar=lambda: reinicios.append(1))
    assert r["nueva"] == "v9.0.0"
    assert (instalacion / "app" / "main.py").read_text() == "# nuevo"
    assert not (instalacion / "app" / "viejo_suelto.py").exists()
    assert (instalacion / "frontend" / "app.js").read_text() == "// nuevo"
    assert (instalacion / "data" / "mio.txt").read_text() == "no tocar"
    from app import db
    assert (db.DB_PATH.parent / "edificios_antes_de_v9.0.0.db").exists()          # copia de la base
    assert (db.DB_PATH.parent / "actualizacion" / "anterior" / "app" / "main.py").read_text() == "# viejo"
    import time
    time.sleep(1.8)
    assert reinicios == [1]


def test_si_la_copia_falla_queda_todo_como_estaba(tmp_path, monkeypatch):
    nueva, instalacion = tmp_path / "nueva", tmp_path / "instalacion"
    for base, texto in ((nueva, "# nuevo"), (instalacion, "# viejo")):
        (base / "app").mkdir(parents=True)
        (base / "app" / "main.py").write_text(texto)
        (base / "frontend").mkdir()
        (base / "frontend" / "app.js").write_text(texto)
    copiar = act.shutil.copytree
    llamadas = []

    def falla_la_segunda(*a, **k):
        llamadas.append(1)
        if len(llamadas) == 2:
            raise OSError("disco lleno")
        return copiar(*a, **k)

    monkeypatch.setattr(act.shutil, "copytree", falla_la_segunda)
    with pytest.raises(OSError):
        act.copiar_version(nueva, instalacion, tmp_path / "respaldo")
    assert (instalacion / "app" / "main.py").read_text() == "# viejo"
    assert (instalacion / "frontend" / "app.js").read_text() == "# viejo"


def test_solo_un_admin_instala(cliente, github):
    cliente.post("/api/usuarios", json={"usuario": "ana", "nombre": "Ana", "password": "123456"})
    t = cliente.post("/api/auth/login", json={"usuario": "ana", "password": "123456"}).json()["token"]
    h = {"Authorization": "Bearer " + t}
    cliente.post("/api/auth/password", json={"actual": "123456", "nueva": "abcdef"}, headers=h)
    assert cliente.post("/api/actualizacion/instalar", headers=h).status_code == 403
    assert not cliente.get("/api/actualizacion", headers=h).json()["preguntar"]


def test_elige_el_paquete_de_su_sistema(monkeypatch):
    nombres = ["edificiosDeMama-v2.0.0.zip", "edificiosDeMama-v2.0.0-windows.zip", "edificiosDeMama-v2.0.0-linux.zip",
               "edificiosDeMama-v2.0.0-macos.zip", "edificiosDeMama-v2.0.0-linux.zip.sha256"]
    assert act.paquete_para(nombres, compilada=False) == "edificiosDeMama-v2.0.0.zip"
    for sistema in ("windows", "linux", "macos"):
        monkeypatch.setattr(act.v, "plataforma", lambda s=sistema: s)
        assert act.paquete_para(nombres, compilada=True) == f"edificiosDeMama-v2.0.0-{sistema}.zip"
    assert act.paquete_para(["edificiosDeMama-v2.0.0.zip"], compilada=True) is None   # sin paquete compilado: no instala


def test_al_descomprimir_el_ejecutable_sigue_siendo_ejecutable(tmp_path):
    origen = tmp_path / "EdificiosDeMama"
    origen.mkdir()
    exe = origen / act.v.EJECUTABLE
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    z = tmp_path / "paquete.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(exe, f"EdificiosDeMama/{exe.name}")
    carpeta = act._extraer(z, tmp_path / "destino", marcador=exe.name)
    assert carpeta == tmp_path / "destino" / "EdificiosDeMama"
    assert (carpeta / exe.name).stat().st_mode & 0o111


def test_compilada_reemplaza_todo_menos_los_datos(tmp_path):
    nueva, instalacion = tmp_path / "nueva", tmp_path / "instalacion"
    (nueva / "_internal").mkdir(parents=True)
    (nueva / "_internal" / "lib.so").write_text("nueva")
    (nueva / act.v.EJECUTABLE).write_text("exe nuevo")
    (instalacion / "_internal").mkdir(parents=True)
    (instalacion / "_internal" / "vieja.so").write_text("vieja")
    (instalacion / act.v.EJECUTABLE).write_text("exe viejo")
    (instalacion / "data").mkdir()
    (instalacion / "data" / "edificios.db").write_text("DATOS")
    act.copiar_version(nueva, instalacion, tmp_path / "respaldo", partes=None)
    assert (instalacion / act.v.EJECUTABLE).read_text() == "exe nuevo"
    assert (instalacion / "_internal" / "lib.so").exists() and not (instalacion / "_internal" / "vieja.so").exists()
    assert (instalacion / "data" / "edificios.db").read_text() == "DATOS"
