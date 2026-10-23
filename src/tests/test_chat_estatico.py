"""La pantalla del chat se sirve desde el propio backend en /chat/."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_sirve_la_pagina():
    r = client.get("/chat/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'id="form-turno"' in r.text


def test_chat_sirve_js_y_css():
    assert client.get("/chat/chat.js").status_code == 200
    assert client.get("/chat/chat.css").status_code == 200


def test_la_api_sigue_en_su_sitio():
    assert client.get("/").json()["chat"] == "/chat/"


def test_el_chat_se_sirve_sin_cache_del_navegador(cliente):
    for ruta in ("/chat/", "/chat/chat.js"):
        r = cliente.get(ruta)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache", ruta
