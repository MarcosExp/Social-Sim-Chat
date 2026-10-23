"""Límites del prototipo, ahora comprobados: clave del terapeuta, historial de correcciones, puerta de predicción real,
última predicción en session_data y campos de la vista que el ER pide (hubo_respuesta)."""
import uuid

import pytest
from sqlalchemy import text

from app.config import settings
from tests.test_api_conversacion import crear
from tests.test_api_dashboard import AUTOR, _sesion_sintetica
from tests.test_er_v2 import _terminar_con, _vista

CLAVE = "clave-de-prueba"
PROTEGIDOS = ["/students", "/sessions", "/predicciones", "/modelo/metricas", "/resumen", "/correcciones", "/conversaciones"]


# ------------------------------------------------------------------------------------------------ clave
def test_con_clave_configurada_los_endpoints_del_terapeuta_exigen_x_api_key(cliente, alumno, monkeypatch):
    monkeypatch.setattr(settings, "api_key_terapeuta", CLAVE)
    for ruta in PROTEGIDOS + [f"/students/{alumno}", f"/students/{alumno}/prediccion", f"/sessions/{uuid.uuid4()}",
                              f"/conversaciones/{uuid.uuid4()}", f"/conversaciones/{uuid.uuid4()}/figuras"]:
        assert cliente.get(ruta).status_code == 401, ruta
        assert cliente.get(ruta, headers={"X-API-Key": "otra"}).status_code == 401, ruta
    assert cliente.get("/resumen", headers={"X-API-Key": CLAVE}).status_code == 200
    assert cliente.patch(f"/sessions/{uuid.uuid4()}/correccion", json={"nota_clinica": "x"}, headers=AUTOR).status_code == 401
    assert cliente.patch(f"/conversaciones/{uuid.uuid4()}/turnos/1", json={"accuracy_corregido": 1}, headers=AUTOR).status_code == 401


def test_el_chat_del_menor_y_la_salud_siguen_abiertos(cliente, alumno, fake, monkeypatch):
    monkeypatch.setattr(settings, "api_key_terapeuta", CLAVE)
    h = cliente.get("/health")
    assert h.status_code == 200 and h.json()["auth_terapeuta"] == "activa"
    assert cliente.get("/").status_code == 200
    ids = [a["student_id"] for a in cliente.get("/conversaciones/alumnos").json()]
    assert alumno in ids
    cid = crear(cliente, alumno)["conversacion_id"]                                   # POST /conversaciones
    assert cliente.post(f"/conversaciones/{cid}/turnos", json={"mensaje": "hola"}).status_code == 200
    # lo que el menor NO puede leer sin clave
    assert cliente.get(f"/conversaciones/{cid}").status_code == 401


def test_la_lista_de_alumnos_del_chat_no_filtra_datos_clinicos(cliente, alumno):
    a = next(x for x in cliente.get("/conversaciones/alumnos").json() if x["student_id"] == alumno)
    assert set(a) == {"student_id", "competencia_objetivo"}


def test_sin_clave_configurada_la_api_queda_abierta_y_lo_dice(cliente, monkeypatch):
    monkeypatch.setattr(settings, "api_key_terapeuta", None)
    assert cliente.get("/resumen").status_code == 200
    assert cliente.get("/health").json()["auth_terapeuta"] == "desactivada"


# ------------------------------------------------------------------------------------------------ historial
def _log(cliente, **p):
    return cliente.get("/correcciones", params=p).json()


def test_cada_correccion_deja_rastro_con_autor_y_valores(cliente, alumno, fake, bd):
    cid = _terminar_con(cliente, fake, alumno, (0,) * 10)
    sid = cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()[0]["session_id"]
    t = next(x for x in cliente.get(f"/conversaciones/{cid}").json()["turnos"]
             if x["rol"] == "menor" and x["tipo"] == "competencia" and x["intento"] == 1)
    url = f"/conversaciones/{cid}/turnos/{t['orden']}"
    assert cliente.patch(url, json={"accuracy_corregido": 2}, headers={"X-Terapeuta": "Ana"}).status_code == 200
    assert cliente.patch(url, json={"accuracy_corregido": 1}, headers={"X-Terapeuta": "Luis"}).status_code == 200
    log = _log(cliente, conversacion_id=cid)
    assert [(r["autor"], r["valor_anterior"], r["valor_nuevo"]) for r in log] == [("Luis", "2", "1"), ("Ana", None, "2")]
    assert all(r["tipo"] == "turno" and r["campo"] == "accuracy_corregido" and r["orden"] == t["orden"] for r in log)

    cliente.patch(f"/sessions/{sid}/correccion", json={"etiqueta_corregida": "estancamiento"}, headers=AUTOR)
    ses = _log(cliente, session_id=sid)
    assert [(r["campo"], r["valor_anterior"], r["valor_nuevo"], r["autor"]) for r in ses] == [("etiqueta_corregida", None, "estancamiento", "Ana Test")]


def test_repetir_el_mismo_valor_no_ensucia_el_historial(cliente, alumno, fake, bd):
    _terminar_con(cliente, fake, alumno, ())
    sid = cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()[0]["session_id"]
    for _ in range(2):
        cliente.patch(f"/sessions/{sid}/correccion", json={"etiqueta_corregida": "progreso"}, headers=AUTOR)
    assert len(_log(cliente, session_id=sid)) == 1


def test_la_nota_clinica_no_se_copia_al_historial(cliente, alumno, fake, bd):
    _terminar_con(cliente, fake, alumno, ())
    sid = cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()[0]["session_id"]
    cliente.patch(f"/sessions/{sid}/correccion", json={"nota_clinica": "texto muy sensible"}, headers=AUTOR)
    [r] = _log(cliente, session_id=sid)
    assert r["campo"] == "nota_clinica" and r["valor_anterior"] is None and r["valor_nuevo"] is None
    with bd.connect() as c:
        assert "sensible" not in str(c.execute(text("SELECT * FROM correccion_log WHERE session_id = CAST(:s AS UUID)"), {"s": sid}).all())


def test_corregir_exige_declarar_quien_corrige(cliente, alumno, fake):
    _terminar_con(cliente, fake, alumno, ())
    sid = cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()[0]["session_id"]
    for h in ({}, {"X-Terapeuta": "   "}):
        assert cliente.patch(f"/sessions/{sid}/correccion", json={"etiqueta_corregida": "progreso"}, headers=h).status_code == 400
    assert cliente.get(f"/sessions/{sid}").json()["etiqueta_corregida"] is None        # no se aplicó nada
    r = cliente.patch(f"/sessions/{sid}/correccion", json={"etiqueta_corregida": "progreso"}, headers={"X-Terapeuta": "x" * 200})
    assert r.status_code == 200 and len(_log(cliente, session_id=sid)[0]["autor"]) == 80


def test_el_historial_se_borra_con_la_sesion_pero_no_bloquea_el_borrado_del_alumno(cliente, alumno, fake, bd):
    _terminar_con(cliente, fake, alumno, ())
    sid = cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()[0]["session_id"]
    cliente.patch(f"/sessions/{sid}/correccion", json={"etiqueta_corregida": "progreso"}, headers=AUTOR)
    assert _log(cliente, session_id=sid)
    # el fixture `alumno` borra al alumno en cascada: no debe fallar por correccion_log


# ------------------------------------------------------------------------------------------------ puerta de predicción
def test_la_prediccion_sobre_sesiones_reales_esta_cerrada_y_explica_por_que(cliente, alumno, fake, bd):
    _terminar_con(cliente, fake, alumno, ())
    d = cliente.get(f"/students/{alumno}/prediccion").json()
    assert d["disponible"] is False and d["ventana_requerida"] == 4
    assert d["sesiones_reales"] == 1 and d["sesiones_sinteticas"] == 0
    texto = " ".join(d["motivos"])
    assert "sesiones reales" in texto and "pct_DET" in texto and "evaluador" in texto
    assert cliente.get("/students/NO-EXISTE/prediccion").status_code == 404


def test_la_puerta_se_abre_sola_cuando_no_quedan_motivos(cliente, alumno, fake, bd, monkeypatch):
    from app import metricas
    monkeypatch.setattr(metricas, "PROVISIONALES", {})
    monkeypatch.setattr(metricas, "PROVISIONALES_EVALUADOR", ())
    for _ in range(4):
        _terminar_con(cliente, fake, alumno, ())
    d = cliente.get(f"/students/{alumno}/prediccion").json()
    assert d["sesiones_reales"] == 4 and d["motivos"] == [] and d["disponible"] is True


def test_las_sesiones_sinteticas_no_cuentan_para_la_ventana_real(cliente, alumno, fake, bd):
    for n in (1, 2, 3, 4):
        _sesion_sintetica(bd, alumno, n)
    _terminar_con(cliente, fake, alumno, ())
    d = cliente.get(f"/students/{alumno}/prediccion").json()
    assert (d["sesiones_reales"], d["sesiones_sinteticas"], d["disponible"]) == (1, 4, False)


# ------------------------------------------------------------------------------------------------ predicción en session_data
def test_guardar_predicciones_rellena_session_data_y_reinicia_lo_anterior(bd, alumno):
    import numpy as np
    import pandas as pd
    from scripts.train_classifier import guardar_predicciones
    a, b = _sesion_sintetica(bd, alumno, 1), _sesion_sintetica(bd, alumno, 2)
    F = pd.DataFrame({"alumno_id": [alumno, alumno], "session_id": [a, b]})
    def pred(sid):
        with bd.connect() as c:
            return c.execute(text("SELECT etiqueta_prediccion, confianza_prediccion FROM session_data "
                                  "WHERE session_id = CAST(:s AS UUID)"), {"s": sid}).one()
    guardar_predicciones(F, np.array(["progreso", "regresion"], dtype=object), np.array([[.9, .1], [.2, .8]]), [False, False], "zz-test-1")
    assert tuple(pred(a)) == ("progreso", 0.9) or float(pred(a)[1]) == 0.9
    assert pred(b)[0] == "regresion"
    # un reentrenamiento sin la sesión b deja su columna vacía en lugar de arrastrar la predicción vieja
    guardar_predicciones(F.iloc[:1], np.array(["estancamiento"], dtype=object), np.array([[.7, .3]]), [False], "zz-test-2")
    assert pred(a)[0] == "estancamiento" and pred(b)[0] is None
    with bd.begin() as c:
        c.execute(text("DELETE FROM classifier_predictions WHERE modelo_version LIKE 'zz-test-%'"))


def test_la_etiqueta_de_prediccion_solo_admite_las_tres_etiquetas(bd, alumno):
    sid = _sesion_sintetica(bd, alumno, 1)
    with pytest.raises(Exception):
        with bd.begin() as c:
            c.execute(text("UPDATE session_data SET etiqueta_prediccion = 'Progreso' WHERE session_id = CAST(:s AS UUID)"), {"s": sid})


# ------------------------------------------------------------------------------------------------ campos del ER en la vista
def test_la_vista_y_la_api_traen_hubo_respuesta_y_es_prueba(cliente, alumno, fake, bd):
    cid = _terminar_con(cliente, fake, alumno, (0, 2, 2, 2, 2))
    assert all(f["hubo_respuesta"] is True and f["es_prueba"] is False for f in _vista(bd, cid))
    assert all(f["hubo_respuesta"] is True for f in cliente.get(f"/conversaciones/{cid}/figuras").json())


def test_el_nombre_del_terapeuta_admite_acentos_codificados_en_la_cabecera(cliente, alumno, fake):
    from urllib.parse import quote
    _terminar_con(cliente, fake, alumno, ())
    sid = cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()[0]["session_id"]
    h = {"X-Terapeuta": quote("María Núñez Álvaro", safe="")}
    assert cliente.patch(f"/sessions/{sid}/correccion", json={"etiqueta_corregida": "progreso"}, headers=h).status_code == 200
    assert _log(cliente, session_id=sid)[0]["autor"] == "María Núñez Álvaro"
