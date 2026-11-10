"""Login y usuarios: contraseña provisoria, siempre un administrador, baja sin borrar."""


def test_login_incorrecto(cliente):
    r = cliente.post("/api/auth/login", json={"usuario": "admin", "password": "mal"})
    assert r.status_code == 401


def test_contrasena_provisoria_obliga_a_cambiarla(cliente):
    cliente.post("/api/usuarios", json={"usuario": "Mama", "nombre": "Mamá", "password": "provisoria"})
    r = cliente.post("/api/auth/login", json={"usuario": "mama", "password": "provisoria"}).json()
    otra = {"Authorization": "Bearer " + r["token"]}
    assert r["usuario"]["debe_cambiar"]
    assert cliente.get("/api/consorcios", headers=otra).status_code == 403
    cliente.post("/api/auth/password", json={"actual": "provisoria", "nueva": "propia123"}, headers=otra)
    assert cliente.get("/api/consorcios", headers=otra).status_code == 200


def test_no_queda_sin_administrador(cliente):
    yo = cliente.get("/api/auth/yo").json()
    r = cliente.put(f"/api/usuarios/{yo['id']}", json={"nombre": "Admin", "es_admin": False})
    assert r.status_code == 400


def test_usuario_repetido(cliente):
    assert cliente.post("/api/usuarios", json={"usuario": "ana", "nombre": "Ana", "password": "123456"}).status_code == 200
    assert cliente.post("/api/usuarios", json={"usuario": "ANA", "nombre": "Otra", "password": "123456"}).status_code == 400


def test_no_admin_no_maneja_usuarios(cliente):
    cliente.post("/api/usuarios", json={"usuario": "ana", "nombre": "Ana", "password": "123456"})
    t = cliente.post("/api/auth/login", json={"usuario": "ana", "password": "123456"}).json()["token"]
    h = {"Authorization": "Bearer " + t}
    cliente.post("/api/auth/password", json={"actual": "123456", "nueva": "abcdef"}, headers=h)
    assert cliente.get("/api/usuarios", headers=h).status_code == 403
