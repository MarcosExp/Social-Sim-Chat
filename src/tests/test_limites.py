"""Límites del prototipo, ahora comprobados: clave del terapeuta, historial de correcciones, puerta de predicción real,
última predicción en session_data, campos de la vista que el ER pide (hubo_respuesta) y límite de sesiones por semana."""
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.config import Settings, settings
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


# ------------------------------------------------------------------------------------------------ límite de sesiones por semana
def _antiguedad(bd, cid, intervalo):
    """Retrasa la apertura de una conversación (created_at) para probar la ventana móvil de 7 días."""
    with bd.begin() as c:
        c.execute(text("UPDATE conversacion SET created_at = now() - CAST(:i AS INTERVAL) WHERE conversacion_id = CAST(:c AS UUID)"),
                  {"i": intervalo, "c": cid})


def _abrir(cliente, alumno, **extra):
    return cliente.post("/conversaciones", json={"student_id": alumno, **extra})


def test_el_limite_de_sesiones_por_semana_esta_apagado_por_defecto(cliente, alumno, fake):
    assert Settings.model_fields["max_sesiones_semana"].default == 0           # lo que arranca sin configurar nada
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_sesiones_semana=-1)                       # un valor negativo es un error de configuración
    for _ in range(6):
        assert _abrir(cliente, alumno).status_code == 201


def test_al_superar_el_limite_semanal_no_se_abre_otra_conversacion(cliente, alumno, fake, bd, monkeypatch):
    monkeypatch.setattr(settings, "max_sesiones_semana", 2)
    primera = crear(cliente, alumno)["conversacion_id"]
    crear(cliente, alumno)
    r = _abrir(cliente, alumno)
    assert r.status_code == 429
    cuerpo = r.json()
    assert cuerpo["codigo"] == "limite_sesiones_semana" and cuerpo["reintentable"] is False
    assert "límite: 2" in cuerpo["mensaje"] and alumno in cuerpo["mensaje"]
    espera = int(r.headers["Retry-After"])
    assert 6 * 86400 < espera <= 7 * 86400                                      # la primera salió de la ventana hace casi 7 días
    with bd.begin() as c:
        assert c.execute(text("SELECT count(*) FROM conversacion WHERE student_id = :s"), {"s": alumno}).scalar() == 2
    # Cerrar la primera no libera el cupo: cuenta lo abierto, no lo terminado.
    for ev in (2, 2, 2, 2, 2, 2, 2, 2):
        fake.respuestas = [ev]
        if turno(cliente, primera, "hola").json().get("estado") == "terminada":
            break
    assert _abrir(cliente, alumno).status_code == 429


def test_el_limite_semanal_es_por_alumno(cliente, alumno, fake, bd, monkeypatch):
    otro = f"{PREFIJO}{uuid.uuid4().hex[:8]}"
    with bd.begin() as c:
        c.execute(text("INSERT INTO student_profile_sim (student_id, competencia_objetivo, trayectoria_disenada, n_sesiones) "
                       "VALUES (:s, 'Metáfora', 'progreso', 0)"), {"s": otro})
    try:
        monkeypatch.setattr(settings, "max_sesiones_semana", 1)
        crear(cliente, alumno)
        assert _abrir(cliente, alumno).status_code == 429
        assert _abrir(cliente, otro).status_code == 201
    finally:
        with bd.begin() as c:
            c.execute(text("DELETE FROM student_profile_sim WHERE student_id = :s"), {"s": otro})


def test_las_conversaciones_de_mas_de_siete_dias_no_cuentan(cliente, alumno, fake, bd, monkeypatch):
    monkeypatch.setattr(settings, "max_sesiones_semana", 2)
    vieja = crear(cliente, alumno)["conversacion_id"]
    crear(cliente, alumno)
    assert _abrir(cliente, alumno).status_code == 429
    _antiguedad(bd, vieja, "8 days")
    assert _abrir(cliente, alumno).status_code == 201                          # la de hace 8 días ya no cuenta


def test_retry_after_dice_cuando_sale_de_la_ventana_la_conversacion_mas_antigua(cliente, alumno, fake, bd, monkeypatch):
    monkeypatch.setattr(settings, "max_sesiones_semana", 2)
    a = crear(cliente, alumno)["conversacion_id"]
    b = crear(cliente, alumno)["conversacion_id"]
    _antiguedad(bd, a, "6 days 23 hours")                                      # sale de la ventana dentro de ~1 hora
    _antiguedad(bd, b, "1 day")
    r = _abrir(cliente, alumno)
    assert r.status_code == 429
    assert 3500 <= int(r.headers["Retry-After"]) <= 3700


def test_las_conversaciones_de_prueba_ni_cuentan_ni_se_bloquean(cliente, alumno, fake, monkeypatch):
    monkeypatch.setattr(settings, "max_sesiones_semana", 1)
    for _ in range(3):
        assert _abrir(cliente, alumno, prueba=True).status_code == 201         # no cuentan para el límite
    assert _abrir(cliente, alumno).status_code == 201                          # la primera real cabe
    assert _abrir(cliente, alumno).status_code == 429                          # la segunda real no
    assert _abrir(cliente, alumno, prueba=True).status_code == 201             # y una de prueba sigue pasando


def test_el_modo_simulado_por_defecto_no_se_bloquea_porque_sus_conversaciones_son_de_prueba(cliente, alumno, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "simulado")
    monkeypatch.setattr(settings, "simulado_registra_sesiones", False)
    monkeypatch.setattr(settings, "max_sesiones_semana", 1)
    for _ in range(3):
        assert _abrir(cliente, alumno).status_code == 201
    monkeypatch.setattr(settings, "simulado_registra_sesiones", True)         # registrando sesiones reales sí se aplica
    assert _abrir(cliente, alumno).status_code == 201
    assert _abrir(cliente, alumno).status_code == 429


def test_los_errores_de_alumno_y_competencia_van_antes_que_el_limite(cliente, alumno, fake, monkeypatch):
    monkeypatch.setattr(settings, "max_sesiones_semana", 1)
    crear(cliente, alumno)
    assert _abrir(cliente, alumno, competencia="Inexistente").status_code == 422
    assert _abrir(cliente, "TST-no-existe").status_code == 404


def test_el_chat_del_menor_conoce_el_codigo_del_limite_semanal():
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "app" / "static" / "chat" / "chat.js").read_text(encoding="utf-8")
    assert "limite_sesiones_semana" in js
