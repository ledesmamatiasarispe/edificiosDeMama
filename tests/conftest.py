"""Cada test usa una base nueva y vacía en una carpeta temporal (nunca la base real)."""
import importlib
import os

os.environ["EDIF_REPO"] = ""   # los tests nunca salen a internet a buscar actualizaciones

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    """Cliente logueado como administrador, sobre una base SIN datos de ejemplo."""
    from app import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "prueba.db")
    db.inicializar(con_ejemplos=False)
    from app import main
    importlib.reload(main)
    c = TestClient(main.app)
    r = c.post("/api/auth/login", json={"usuario": "admin", "password": "admin"})
    c.headers["Authorization"] = "Bearer " + r.json()["token"]
    c.post("/api/auth/password", json={"actual": "admin", "nueva": "clave-nueva"})
    return c


@pytest.fixture
def base_ejemplos(tmp_path, monkeypatch):
    from app import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "ejemplos.db")
    db.inicializar(con_ejemplos=True)
    return db
