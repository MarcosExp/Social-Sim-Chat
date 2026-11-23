"""NF4: la API devuelve todos sus errores como `{codigo, mensaje, reintentable}` (antes, validación y fallos internos no)."""
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_db
from app.errores import resumir_errores
from app.main import app


def _forma(j):
    assert set(("codigo", "mensaje", "reintentable")) <= set(j), j
    assert isinstance(j["mensaje"], str) and j["mensaje"]


def test_un_turno_vacio_da_422_con_el_formato_del_contrato_y_conserva_detail(cliente, alumno):
    cid = cliente.post("/conversaciones", json={"student_id": alumno, "prueba": True}).json()["conversacion_id"]
    r = cliente.post(f"/conversaciones/{cid}/turnos", json={"mensaje": "   "})
    assert r.status_code == 422
    j = r.json()
    _forma(j)
    assert j["codigo"] == "validacion" and j["reintentable"] is False
    assert "mensaje" in j["mensaje"] and "vacío" in j["mensaje"]
    assert isinstance(j["detail"], list) and j["detail"]          # compatibilidad con quien leía FastAPI «a pelo»


def test_un_turno_demasiado_largo_dice_el_maximo(cliente, alumno):
    cid = cliente.post("/conversaciones", json={"student_id": alumno, "prueba": True}).json()["conversacion_id"]
    j = cliente.post(f"/conversaciones/{cid}/turnos", json={"mensaje": "x" * 501}).json()
    assert "máximo 500" in j["mensaje"]


def test_un_id_de_conversacion_mal_formado_da_422_legible(cliente):
    r = cliente.get("/conversaciones/esto-no-es-un-uuid")
    assert r.status_code == 422 and r.json()["codigo"] == "validacion"


def test_crear_sin_alumno_o_con_alumno_en_blanco_da_422(cliente):
    assert cliente.post("/conversaciones", json={}).status_code == 422
    r = cliente.post("/conversaciones", json={"student_id": "   "})
    assert r.status_code == 422 and "student_id" in r.json()["mensaje"]


def test_un_alias_o_competencia_en_blanco_equivale_a_omitirlos(cliente, alumno):
    r = cliente.post("/conversaciones", json={"student_id": alumno, "alias": "   ", "competencia": "", "prueba": True})
    assert r.status_code == 201
    j = r.json()
    assert j["competencia"] == "Metáfora"                          # la del alumno
    assert alumno in j["turno_bot"]["texto"]                       # alias = student_id, no un saludo sin nombre


def test_el_alias_se_recorta(cliente, alumno):
    r = cliente.post("/conversaciones", json={"student_id": alumno, "alias": "  Ana  ", "prueba": True})
    assert r.status_code == 201 and "Ana" in r.json()["turno_bot"]["texto"] and "  Ana" not in r.json()["turno_bot"]["texto"]


def test_base_de_datos_caida_da_503_reintentable_con_retry_after(cliente):
    def _bd_caida():
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))
        yield  # pragma: no cover
    app.dependency_overrides[get_db] = _bd_caida
    try:
        r = cliente.get("/conversaciones/alumnos")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 503 and r.headers["Retry-After"] == "5"
    j = r.json()
    _forma(j)
    assert j["codigo"] == "bd_no_disponible" and j["reintentable"] is True
    assert "connection refused" not in r.text                      # no se filtran detalles internos


def test_un_error_no_previsto_da_500_json_sin_filtrar_detalles(bd, fake, monkeypatch):
    import app.routers.resumen as resumen

    def _rompe(*a, **k):
        raise RuntimeError("secreto interno: password=hunter2")
    monkeypatch.setattr(resumen, "select", _rompe)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/resumen")
    assert r.status_code == 500
    j = r.json()
    _forma(j)
    assert j["codigo"] == "error_interno" and "hunter2" not in r.text


def test_resumen_de_errores_limita_a_tres():
    errs = [{"loc": ("body", f"c{i}"), "type": "missing", "msg": "x"} for i in range(5)]
    t = resumir_errores(errs)
    assert t.count("falta") == 3 and "y 2 más" in t
