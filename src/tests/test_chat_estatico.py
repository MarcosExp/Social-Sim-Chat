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


# ------------------------------------------------------------------------------------------------ NF4: accesibilidad del chat
import re  # noqa: E402
from pathlib import Path  # noqa: E402

CHAT = Path(__file__).resolve().parents[1] / "app" / "static" / "chat"


def _luminancia(hex_):
    h = hex_.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4   # noqa: E731  (fórmula WCAG 2.x)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contraste(a, b):
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _variables(bloque_css):
    """Variables CSS de color de un bloque (admite #rgb y #rrggbb; las de 3 cifras se expanden)."""
    out = {}
    for nombre, h in re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?)\b", bloque_css):
        out[nombre] = "#" + "".join(c * 2 for c in h[1:]) if len(h) == 4 else h
    return out


def _tema(selector):
    css = (CHAT / "chat.css").read_text(encoding="utf-8")
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}|" + re.escape(selector) + r"\s*\{([^}]*)\}", css, re.S)
    return _variables(m.group(1) or m.group(2))


def test_contraste_de_texto_del_tema_normal_cumple_AA():
    v = _tema(":root")
    pares = [("texto", "fondo"), ("texto", "bot"), ("texto", "menor"), ("suave", "fondo"), ("suave", "bot"), ("suave", "menor"),
             ("primario-texto", "primario"), ("error", "error-fondo"), ("primario", "fondo")]
    for fg, bg in pares:
        c = _contraste(v[fg], v["fondo"] if bg == "fondo" else v[bg])
        assert c >= 4.5, f"{fg} sobre {bg}: {c:.2f}"
    assert _contraste(v["suave"], "#ffffff") >= 4.5          # la etiqueta «ayuda» va sobre blanco


def test_contraste_de_componentes_y_foco_cumple_1_4_11():
    """Bordes de campos y anillo de foco: >= 3:1 sobre blanco y sobre el fondo (antes 1,5:1 y 1,9:1)."""
    v = _tema(":root")
    for clave in ("borde-campo", "foco"):
        for fondo in ("#ffffff", v["fondo"]):
            assert _contraste(v[clave], fondo) >= 3.0, f"{clave} sobre {fondo}"


def test_el_tema_de_alto_contraste_llega_a_AAA():
    v = {**_tema(":root"), **_tema('html[data-contraste="alto"]')}
    for fg, bg in [("texto", "fondo"), ("suave", "fondo"), ("primario-texto", "primario"), ("error", "error-fondo"), ("foco", "fondo")]:
        assert _contraste(v[fg], v[bg]) >= 7.0, f"{fg} sobre {bg}: {_contraste(v[fg], v[bg]):.2f}"
    assert _contraste(v["borde-campo"], "#ffffff") >= 7.0


def test_el_html_trae_los_apoyos_de_accesibilidad():
    h = (CHAT / "index.html").read_text(encoding="utf-8")
    assert '<html lang="es">' in h
    assert 'class="saltar" href="#contenido"' in h and '<main id="contenido" tabindex="-1">' in h
    assert 'role="group" aria-label="Ajustes de lectura"' in h
    assert 'id="btn-contraste" type="button" class="ajuste" aria-pressed="false"' in h
    assert 'aria-label="Letra más pequeña"' in h and 'aria-label="Letra más grande"' in h
    assert 'aria-describedby="error-inicio"' in h and 'aria-describedby="estado contador"' in h
    for ident in ("error-inicio", "estado", "contador", "aviso-ajustes"):
        assert f'id="{ident}"' in h, ident                  # lo que apuntan aria-describedby y el aviso de ajustes existe


def test_el_objetivo_de_las_casillas_mide_al_menos_24_px():
    css = (CHAT / "chat.css").read_text(encoding="utf-8")
    m = re.search(r"input\[type=checkbox\]\s*\{\s*width:\s*(\d+)px;\s*height:\s*(\d+)px", css)
    assert m and int(m.group(1)) >= 24 and int(m.group(2)) >= 24


def test_el_chat_nunca_enseña_json_crudo_al_menor():
    js = (CHAT / "chat.js").read_text(encoding="utf-8")
    assert "JSON.stringify(datos.detail)" not in js
    for codigo in ("validacion", "bd_no_disponible", "error_interno"):
        assert re.search(rf"\b{codigo}:\s*\"", js), codigo   # todos los códigos de error nuevos tienen mensaje propio


def test_los_ajustes_de_lectura_no_guardan_datos_del_alumno():
    js = (CHAT / "chat.js").read_text(encoding="utf-8")
    usos = re.findall(r"localStorage\.(?:get|set)Item\(([^,)]*)", js)
    assert usos and set(usos) == {"CLAVE_AJUSTES"}           # el único dato que toca el almacenamiento local son los ajustes de pantalla
