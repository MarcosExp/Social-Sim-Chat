"""ADR-003: el dashboard solo habla con la API. Endpoints de lectura (resumen, predicciones, modelo, listado de
conversaciones, figuras) y de escritura (correcciones del terapeuta, con recálculo de métricas)."""
import json
import uuid

import pytest
from sqlalchemy import text

from app.config import settings
from tests.test_api_conversacion import crear, turno
from tests.test_er_v2 import _terminar_con


AUTOR = {"X-Terapeuta": "Ana Test"}


def _sesion_sintetica(bd, alumno, n, etiqueta="progreso"):
    sid = uuid.uuid4()
    with bd.begin() as c:
        c.execute(text(
            "INSERT INTO session_data (session_id, student_id, sesion_num, competencia, origen, amlu, "
            "latencia_pragmatica_ms, irc_pct, pepe, pct_det, etiqueta_real_disenada) "
            "VALUES (:i, :s, :n, 'Metáfora', 'sintetico', 3, 4000, 20, 1, 50, :e)"), {"i": sid, "s": alumno, "n": n, "e": etiqueta})
    return sid


def _prediccion(bd, alumno, sid, version, etiqueta="progreso", alerta=False):
    with bd.begin() as c:
        c.execute(text(
            "INSERT INTO classifier_predictions (student_id, session_id, modelo_version, etiqueta_predicha, confianza, "
            "es_estancamiento_operacional) VALUES (:s, :i, :v, :e, 0.8, :a)"),
            {"s": alumno, "i": sid, "v": version, "e": etiqueta, "a": alerta})


# ------------------------------------------------------------------------------------------------ lectura
def test_resumen_cuenta_lo_que_hay(cliente, alumno, bd):
    antes = cliente.get("/resumen").json()
    sid = _sesion_sintetica(bd, alumno, 1, "estancamiento")
    _prediccion(bd, alumno, sid, "zzzz-v1")
    d = cliente.get("/resumen").json()
    assert d["sesiones_sinteticas"] == antes["sesiones_sinteticas"] + 1
    assert d["predicciones"] == antes["predicciones"] + 1 and d["alumnos"] == antes["alumnos"]   # el alumno ya existía
    assert d["sesiones_sinteticas_por_etiqueta"]["estancamiento"] == antes["sesiones_sinteticas_por_etiqueta"].get("estancamiento", 0) + 1
    assert d["alumnos_por_trayectoria"]["progreso"] >= 1 and d["ultima_version_modelo"] >= "zzzz-v1"


def test_predicciones_por_defecto_solo_la_ultima_version(cliente, alumno, bd):
    s1, s2 = _sesion_sintetica(bd, alumno, 1), _sesion_sintetica(bd, alumno, 2)
    _prediccion(bd, alumno, s1, "zzzz-v1"); _prediccion(bd, alumno, s1, "zzzz-v2", "estancamiento", True)
    _prediccion(bd, alumno, s2, "zzzz-v2")
    ultima = cliente.get("/predicciones", params={"student_id": alumno}).json()
    assert {p["modelo_version"] for p in ultima} == {"zzzz-v2"} and len(ultima) == 2
    assert any(p["es_estancamiento_operacional"] and p["etiqueta_predicha"] == "estancamiento" for p in ultima)
    todas = cliente.get("/predicciones", params={"student_id": alumno, "todas_las_versiones": True}).json()
    assert len(todas) == 3
    una = cliente.get("/predicciones", params={"student_id": alumno, "modelo_version": "zzzz-v1"}).json()
    assert len(una) == 1 and una[0]["session_id"] == str(s1)


def test_modelo_metricas_sirve_el_json_o_404(cliente, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "metrics_path", tmp_path / "no_existe.json")
    r = cliente.get("/modelo/metricas")
    assert r.status_code == 404 and r.json()["codigo"] == "modelo_no_entrenado"
    f = tmp_path / "metrics.json"
    f.write_text(json.dumps({"modelo_version": "v-test", "f1_macro": 0.79}), encoding="utf-8")
    monkeypatch.setattr(settings, "metrics_path", f)
    assert cliente.get("/modelo/metricas").json() == {"modelo_version": "v-test", "f1_macro": 0.79}


def test_listado_de_conversaciones_oculta_pruebas(cliente, alumno, fake, bd):
    real = _terminar_con(cliente, fake, alumno, ())
    prueba = crear(cliente, alumno, prueba=True)["conversacion_id"]
    ids = lambda **p: {c["conversacion_id"] for c in cliente.get("/conversaciones", params={"student_id": alumno, **p}).json()}   # noqa: E731
    assert ids() == {real}
    assert ids(incluir_pruebas=True) == {real, prueba}
    assert ids(estado="en_curso", incluir_pruebas=True) == {prueba}


def test_figuras_por_api(cliente, alumno, fake, bd):
    cid = _terminar_con(cliente, fake, alumno, (0, 2, 2, 2, 2))
    f = cliente.get(f"/conversaciones/{cid}/figuras").json()
    comp = [x for x in f if x["tipo"] == "competencia"]
    assert comp[0]["accuracy_score"] == 1 and comp[0]["n_intentos"] == 2 and all(x["accuracy_score"] == 2 for x in comp[1:])
    assert cliente.get(f"/conversaciones/{uuid.uuid4()}/figuras").status_code == 404


def test_detalle_de_conversacion_trae_campos_de_correccion(cliente, alumno, fake):
    cid = _terminar_con(cliente, fake, alumno, ())
    t = [x for x in cliente.get(f"/conversaciones/{cid}").json()["turnos"] if x["rol"] == "menor"][0]
    assert {"iniciativa", "accuracy_corregido", "ayudas_solicitadas"} <= set(t) and t["accuracy_corregido"] is None


def test_session_data_ya_no_tiene_columna_turnos(cliente, alumno, bd):
    """Migración 012: los turnos viven solo en conversacion_turno (vista turn_data); ni la tabla ni el listado los exponen."""
    _sesion_sintetica(bd, alumno, 1)
    with bd.connect() as c:
        hay = c.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_name = 'session_data' AND column_name = 'turnos'")).scalar()
    assert hay == 0
    fila = cliente.get("/sessions", params={"student_id": alumno}).json()[0]
    assert "turnos" not in fila


# ---------------------------------------------------------------------------------------------- escritura
def _turnos(cliente, cid):
    return cliente.get(f"/conversaciones/{cid}").json()["turnos"]


def test_corregir_turno_recalcula_la_sesion_y_conserva_el_original(cliente, alumno, fake, bd):
    cid = _terminar_con(cliente, fake, alumno, (0,) * 10)                     # todo 0 (también tras la ayuda): PEPE = 0
    sesion0 = cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()[0]
    assert sesion0["PEPE"] == 0.0
    t = [x for x in _turnos(cliente, cid) if x["rol"] == "menor" and x["tipo"] == "competencia" and x["intento"] == 1][0]
    r = cliente.patch(f"/conversaciones/{cid}/turnos/{t['orden']}", json={"accuracy_corregido": 2}, headers=AUTOR)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["turno"]["evaluacion"] == 0 and d["turno"]["accuracy_corregido"] == 2      # el original se conserva
    assert d["sesion"]["PEPE"] > 0 and d["sesion"]["n_figuras"] == sesion0["n_figuras"]
    assert d["sesion"]["session_id"] == sesion0["session_id"]
    # coincide con lo que lee el dashboard después
    assert cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()[0]["PEPE"] == d["sesion"]["PEPE"]
    # quitar la corrección devuelve las métricas originales
    r2 = cliente.patch(f"/conversaciones/{cid}/turnos/{t['orden']}", json={"accuracy_corregido": None}, headers=AUTOR).json()
    assert r2["turno"]["accuracy_corregido"] is None and r2["sesion"]["PEPE"] == 0.0


def test_corregir_turno_valida_el_caso(cliente, alumno, fake, bd):
    cid = _terminar_con(cliente, fake, alumno, ())
    ts = _turnos(cliente, cid)
    bot = next(x for x in ts if x["rol"] != "menor")
    apertura = next(x for x in ts if x["rol"] == "menor" and x["evaluacion"] is None)
    comp = next(x for x in ts if x["rol"] == "menor" and x["evaluacion"] is not None)
    url = lambda o: f"/conversaciones/{cid}/turnos/{o}"                                           # noqa: E731
    assert cliente.patch(url(bot["orden"]), json={"accuracy_corregido": 1}, headers=AUTOR).json()["codigo"] == "turno_no_valorable"
    assert cliente.patch(url(apertura["orden"]), json={"accuracy_corregido": 1}, headers=AUTOR).status_code == 409
    assert cliente.patch(url(9999), json={"accuracy_corregido": 1}, headers=AUTOR).status_code == 404
    assert cliente.patch(url(comp["orden"]), json={"accuracy_corregido": 3}, headers=AUTOR).status_code == 422
    assert cliente.patch(url(comp["orden"]), json={}, headers=AUTOR).status_code == 422                          # el campo es obligatorio
    assert cliente.patch(f"/conversaciones/{uuid.uuid4()}/turnos/1", json={"accuracy_corregido": 1}, headers=AUTOR).status_code == 404


def test_no_se_corrige_una_conversacion_en_curso(cliente, alumno, fake):
    cid = crear(cliente, alumno)["conversacion_id"]
    turno(cliente, cid, "hola")
    r = cliente.patch(f"/conversaciones/{cid}/turnos/2", json={"accuracy_corregido": 1}, headers=AUTOR)
    assert r.status_code == 409 and r.json()["codigo"] == "conversacion_en_curso"


def test_corregir_sesion_etiqueta_y_nota_clinica(cliente, alumno, fake, bd):
    _terminar_con(cliente, fake, alumno, ())
    lista = cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()
    sid = lista[0]["session_id"]
    assert "nota_clinica" not in lista[0]                                                         # no sale en los listados
    r = cliente.patch(f"/sessions/{sid}/correccion", json={"etiqueta_corregida": "estancamiento", "nota_clinica": "se frustra"}, headers=AUTOR)
    assert r.status_code == 200 and r.json()["etiqueta_corregida"] == "estancamiento" and r.json()["nota_clinica"] == "se frustra"
    # solo cambia lo enviado
    r = cliente.patch(f"/sessions/{sid}/correccion", json={"nota_clinica": None}, headers=AUTOR).json()
    assert r["nota_clinica"] is None and r["etiqueta_corregida"] == "estancamiento"
    assert cliente.get(f"/sessions/{sid}").json()["etiqueta_corregida"] == "estancamiento"
    assert cliente.patch(f"/sessions/{sid}/correccion", json={"etiqueta_corregida": "Regresión"}, headers=AUTOR).status_code == 422
    assert cliente.patch(f"/sessions/{sid}/correccion", json={}, headers=AUTOR).status_code == 422
    assert cliente.patch(f"/sessions/{uuid.uuid4()}/correccion", json={"nota_clinica": "x"}, headers=AUTOR).status_code == 404
