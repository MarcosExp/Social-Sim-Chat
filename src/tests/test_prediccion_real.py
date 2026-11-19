"""Predicción del clasificador sobre sesiones REALES (modelo de servicio sin %DET; `app/prediccion.py`).

Cubre lo que pidió Marcos (19/11/2026): el joblib guarda la MISMA lista de features que construye la inferencia, la versión
del modelo deja claro que va sin %DET, las sesiones 1 a 3 no se predicen, la alerta de tres sesiones usa las predicciones
anteriores, y la predicción se declara orientativa."""
import uuid

import joblib
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from app import metricas, ml_config, prediccion
from tests.conftest import escribir_modelo_servicio
from tests.test_api_conversacion import crear, turno
from tests.test_er_v2 import _terminar_con


def _sesion_real(bd, alumno, n, competencia="Metáfora", amlu=3.0, pepe=1.0, irc=20.0, lpp=4000):
    """Sesión REAL (la BD exige una conversación enlazada: `session_data_origen_conversacion_check`)."""
    sid, cid = uuid.uuid4(), uuid.uuid4()
    with bd.begin() as c:
        c.execute(text(
            "INSERT INTO conversacion (conversacion_id, student_id, competencia, personaje, alias, estado, nodo_actual, guion_version, "
            "es_prueba) VALUES (:c, :s, :k, 'Personaje', 'Alias', 'terminada', 'fin', 'test', false)"),
            {"c": cid, "s": alumno, "k": competencia})
        c.execute(text(
            "INSERT INTO session_data (session_id, student_id, sesion_num, competencia, origen, conversacion_id, amlu, "
            "latencia_pragmatica_ms, irc_pct, pepe, pct_det) VALUES (:i, :s, :n, :k, 'real', :c, :a, :l, :r, :p, 50)"),
            {"i": sid, "s": alumno, "n": n, "k": competencia, "c": cid, "a": amlu, "l": lpp, "r": irc, "p": pepe})
    return sid


def _filas(bd, alumno):
    with bd.connect() as c:
        return c.execute(text(
            "SELECT s.sesion_num, p.modelo_version, p.etiqueta_predicha, p.confianza, p.es_estancamiento_operacional, "
            "s.etiqueta_prediccion FROM classifier_predictions p JOIN session_data s USING (session_id) "
            "WHERE p.student_id = :s ORDER BY s.sesion_num, p.modelo_version"), {"s": alumno}).all()


# ------------------------------------------------------------------------------------------------ el joblib y la inferencia
def _corpus_minimo(n_alumnos=40, n_ses=8):
    rng = np.random.default_rng(0)
    clases = ["estancamiento", "progreso", "regresion"]
    filas = []
    for a in range(n_alumnos):
        et = clases[a % 3]
        for s in range(1, n_ses + 1):
            filas.append({"alumno_id": f"A{a}", "competencia": "Metáfora", "sesion": s, "etiqueta": et,
                          "aMLU": 3 + 0.1 * s * (et == "progreso") + rng.normal(0, .1),
                          "latencia_pragmatica_ms": 4000 + rng.normal(0, 200), "IRC_pct": 20 + rng.normal(0, 3),
                          "PEPE": 1 + 0.05 * s * (et == "progreso") + rng.normal(0, .05), "pct_DET": 50 + rng.normal(0, 5)})
    return pd.DataFrame(filas)


def test_el_joblib_guarda_las_mismas_features_que_construye_la_inferencia(tmp_path, monkeypatch):
    from scripts.train_classifier import modelo_servicio
    paquete, resumen = modelo_servicio(_corpus_minimo(), seed=1, version=f"rf-vent4-{ml_config.SUFIJO_VERSION_SERVICIO}-prueba")
    ruta = tmp_path / "classifier.joblib"
    joblib.dump({"servicio": paquete}, ruta)
    guardado = joblib.load(ruta)["servicio"]

    esperadas = ml_config.columnas_features_servicio()
    assert guardado["features"] == esperadas == resumen["features"]                 # misma lista y MISMO ORDEN
    assert len(esperadas) == 3 * len(ml_config.metricas_servicio()) == 12
    assert not any(c.startswith("pct_DET") for c in esperadas)                      # sin %DET
    assert guardado["modelo"].n_features_in_ == len(esperadas)

    # y la construcción de features de la inferencia produce exactamente esas columnas, en ese orden
    F = ml_config.construir_features_servicio(_corpus_minimo(3, 5))
    assert [c for c in F.columns if c in esperadas] == esperadas

    monkeypatch.setattr(prediccion, "RUTA", ruta)
    servicio, motivo = prediccion._validar(joblib.load(ruta))
    assert servicio is not None and motivo == ""


def test_el_modelo_de_15_features_y_el_de_servicio_son_distintos():
    assert ml_config.columnas_features() != ml_config.columnas_features_servicio()
    assert set(ml_config.columnas_features_servicio()) < set(ml_config.columnas_features())
    assert set(ml_config.columnas_features()) - set(ml_config.columnas_features_servicio()) == {
        "pct_DET_media", "pct_DET_pendiente", "pct_DET_dif_base"}


def test_la_config_de_servicio_sigue_lo_que_marca_metricas_como_provisional(monkeypatch):
    """Una sola fuente de verdad: si %DET deja de ser provisional (`metricas.PROVISIONALES`), entra en el modelo de servicio."""
    assert "pct_DET" not in ml_config.metricas_servicio()
    monkeypatch.setattr(metricas, "PROVISIONALES", {})
    ml_config.config_servicio.cache_clear()
    try:
        assert "pct_DET" in ml_config.metricas_servicio() and len(ml_config.columnas_features_servicio()) == 15
    finally:
        ml_config.config_servicio.cache_clear()


def test_se_rechaza_un_joblib_con_otras_features_o_sin_modelo_de_servicio(tmp_path):
    cols = ml_config.columnas_features_servicio()
    mal_orden = tmp_path / "a.joblib"; escribir_modelo_servicio(mal_orden, features=cols[::-1])
    con_det = tmp_path / "b.joblib"; escribir_modelo_servicio(con_det, features=ml_config.columnas_features())
    sin_det_en_version = tmp_path / "c.joblib"; escribir_modelo_servicio(sin_det_en_version, version="rf-vent4-20261119")
    for f in (mal_orden, con_det, sin_det_en_version):
        servicio, motivo = prediccion._validar(joblib.load(f))
        assert servicio is None and "make train" in motivo or "sinDET" in motivo or "%DET" in motivo
    assert prediccion._validar({"modelo": object(), "features": cols})[0] is None   # joblib antiguo: sin clave `servicio`
    assert prediccion._validar(object())[0] is None


def test_un_joblib_corrupto_no_tumba_la_api(cliente, tmp_path, monkeypatch):
    ruta = tmp_path / "classifier.joblib"
    ruta.write_bytes(b"esto no es un joblib")
    monkeypatch.setattr(prediccion, "RUTA", ruta)
    monkeypatch.setattr(prediccion, "_cache", {"firma": None, "paquete": None, "motivo": ""})
    h = cliente.get("/health").json()
    assert h["clasificador"].startswith("no disponible") and "no se pudo leer" in h["clasificador"]
    assert prediccion.cargar() is None


# ------------------------------------------------------------------------------------------------ /health
def test_health_informa_del_clasificador_sin_cambiar_el_estado_general(cliente, modelo_servicio, sin_modelo):
    # sin_modelo se aplica después de modelo_servicio: el fichero no existe
    h = cliente.get("/health").json()
    assert h["clasificador"].startswith("no disponible") and "make train" in h["clasificador"]
    assert h["status"] == "ok" and h["database"] == "ok"             # el clasificador es informativo


def test_health_con_modelo_da_la_version(cliente, modelo_servicio):
    modelo_servicio(version="rf-vent4-sinDET-20261119-000000")
    assert cliente.get("/health").json()["clasificador"] == "ok: rf-vent4-sinDET-20261119-000000"


def test_si_el_fichero_cambia_se_vuelve_a_cargar(cliente, modelo_servicio):
    modelo_servicio(version="rf-vent4-sinDET-v1")
    assert prediccion.estado() == "ok: rf-vent4-sinDET-v1"
    ruta = modelo_servicio(version="rf-vent4-sinDET-v2")
    assert prediccion.estado() == "ok: rf-vent4-sinDET-v2" and ruta.exists()


# ------------------------------------------------------------------------------------------------ ventana y alerta
def test_las_sesiones_1_a_3_no_se_predicen_y_de_la_4_en_adelante_si(cliente, alumno, bd, modelo_servicio):
    modelo_servicio("progreso")
    for n in range(1, 6):
        _sesion_real(bd, alumno, n)
    d = cliente.get(f"/students/{alumno}/prediccion").json()
    assert d["disponible"] is True and d["orientativa"] is True and d["modelo_version"] == "rf-vent4-sinDET-test"
    assert [p["sesion_num"] for p in d["predicciones"]] == [4, 5] and d["motivos"] == []
    assert all(p["etiqueta_predicha"] == "progreso" and p["competencia"] == "Metáfora" for p in d["predicciones"])
    assert d["sesiones_reales"] == 5


def test_con_tres_sesiones_reales_no_hay_prediccion(cliente, alumno, bd, modelo_servicio):
    modelo_servicio()
    for n in range(1, 4):
        _sesion_real(bd, alumno, n)
    d = cliente.get(f"/students/{alumno}/prediccion").json()
    assert d["disponible"] is False and d["predicciones"] == [] and "4 sesiones reales" in d["motivos"][0]


def test_la_ventana_se_forma_por_competencia(cliente, alumno, bd, modelo_servicio):
    """Cuatro sesiones repartidas entre dos competencias no forman ventana en ninguna."""
    modelo_servicio()
    for n, comp in enumerate(["Metáfora", "Sarcasmo", "Metáfora", "Sarcasmo"], start=1):
        _sesion_real(bd, alumno, n, comp)
    d = cliente.get(f"/students/{alumno}/prediccion").json()
    assert d["disponible"] is False and "Metáfora: 2" in d["motivos"][0] and "Sarcasmo: 2" in d["motivos"][0]


def test_la_alerta_necesita_tres_predicciones_seguidas_de_no_progreso(cliente, alumno, bd, modelo_servicio):
    """Sesiones 4, 5 y 6 con predicción: la alerta salta en la 6 (racha de 3), no antes."""
    modelo_servicio("estancamiento")
    for n in range(1, 7):
        _sesion_real(bd, alumno, n)
    alertas = {p["sesion_num"]: p["es_estancamiento_operacional"]
               for p in cliente.get(f"/students/{alumno}/prediccion").json()["predicciones"]}
    assert alertas == {4: False, 5: False, 6: True}


def test_sin_no_progreso_no_hay_alerta(cliente, alumno, bd, modelo_servicio):
    modelo_servicio("progreso")
    for n in range(1, 8):
        _sesion_real(bd, alumno, n)
    assert not any(p["es_estancamiento_operacional"] for p in cliente.get(f"/students/{alumno}/prediccion").json()["predicciones"])


def test_una_metrica_nula_deja_esa_sesion_sin_prediccion_y_lo_explica(cliente, alumno, bd, modelo_servicio):
    modelo_servicio()
    for n in range(1, 6):
        _sesion_real(bd, alumno, n, amlu=None if n == 5 else 3.0)
    d = cliente.get(f"/students/{alumno}/prediccion").json()
    assert [p["sesion_num"] for p in d["predicciones"]] == [4] and "sesión(es) 5" in " ".join(d["motivos"])


def test_las_sinteticas_nunca_entran_en_la_ventana_real(cliente, alumno, bd, modelo_servicio):
    from tests.test_api_dashboard import _sesion_sintetica
    modelo_servicio()
    for n in range(1, 8):
        _sesion_sintetica(bd, alumno, n)
    for n in range(8, 11):
        _sesion_real(bd, alumno, n)                          # la numeración continúa, pero solo hay 3 reales
    d = cliente.get(f"/students/{alumno}/prediccion").json()
    assert (d["disponible"], d["sesiones_reales"], d["sesiones_sinteticas"]) == (False, 3, 7)


def test_se_avisa_de_las_features_fuera_del_rango_de_entrenamiento(cliente, alumno, bd, modelo_servicio):
    cols = ml_config.columnas_features_servicio()
    rangos = {c: [-1e9, 1e9] for c in cols}
    rangos["latencia_pragmatica_ms_media"] = [0.0, 1.0]       # las sesiones de prueba tienen 4000/5000 = 0,8 normalizado
    modelo_servicio(rangos=rangos)
    for n in range(1, 5):
        _sesion_real(bd, alumno, n, lpp=9000)                 # 9000/5000 = 1,8 > 1,0
    p = cliente.get(f"/students/{alumno}/prediccion").json()["predicciones"][0]
    assert p["fuera_de_rango"] == ["latencia_pragmatica_ms_media"]


def test_la_respuesta_siempre_declara_que_es_orientativa_y_no_validada(cliente, alumno, bd, modelo_servicio):
    modelo_servicio()
    for n in range(1, 5):
        _sesion_real(bd, alumno, n)
    d = cliente.get(f"/students/{alumno}/prediccion").json()
    texto = " ".join(d["avisos"])
    assert d["orientativa"] is True
    assert "sintéticos" in texto and "menores reales" in texto and "escalas" in texto and "%DET" in texto


# ------------------------------------------------------------------------------------------------ guardado
def test_guardar_escribe_historial_y_ultima_prediccion_y_es_idempotente(alumno, bd, modelo_servicio):
    from app.db import SessionLocal
    modelo_servicio("estancamiento")
    for n in range(1, 6):
        _sesion_real(bd, alumno, n)
    with SessionLocal() as db:
        assert prediccion.guardar(db, alumno) == 2
        assert prediccion.guardar(db, alumno) == 2             # repetir no duplica (UNIQUE session_id, modelo_version)
    f = _filas(bd, alumno)
    assert [(r[0], r[1], r[2], float(r[3]), r[5]) for r in f] == [
        (4, "rf-vent4-sinDET-test", "estancamiento", 1.0, "estancamiento"),
        (5, "rf-vent4-sinDET-test", "estancamiento", 1.0, "estancamiento")]
    with bd.connect() as c:
        sin = c.execute(text("SELECT count(*) FROM session_data WHERE student_id = :s AND sesion_num <= 3 "
                             "AND etiqueta_prediccion IS NOT NULL"), {"s": alumno}).scalar()
    assert sin == 0                                            # las sesiones 1-3 quedan sin predicción


def test_una_version_nueva_conserva_el_historial_de_la_anterior(alumno, bd, modelo_servicio):
    from app.db import SessionLocal
    for n in range(1, 5):
        _sesion_real(bd, alumno, n)
    with SessionLocal() as db:
        modelo_servicio("progreso", version="rf-vent4-sinDET-v1"); prediccion.guardar(db, alumno)
        modelo_servicio("regresion", version="rf-vent4-sinDET-v2"); prediccion.guardar(db, alumno)
    f = _filas(bd, alumno)
    assert [(r[1], r[2]) for r in f] == [("rf-vent4-sinDET-v1", "progreso"), ("rf-vent4-sinDET-v2", "regresion")]
    assert f[0][5] == "regresion"                              # session_data guarda la última


def test_sin_modelo_guardar_no_hace_nada(alumno, bd, sin_modelo):
    from app.db import SessionLocal
    for n in range(1, 6):
        _sesion_real(bd, alumno, n)
    with SessionLocal() as db:
        assert prediccion.guardar(db, alumno) == 0
    assert _filas(bd, alumno) == []


def test_el_listado_devuelve_la_ultima_version_de_cada_origen(cliente, alumno, bd, modelo_servicio):
    """«rf-vent4-sinDET-…» ordena alfabéticamente por delante de «rf-vent4-2026…»: sin separar por origen taparía a la sintética."""
    from app.db import SessionLocal
    from tests.test_api_dashboard import _prediccion, _sesion_sintetica
    modelo_servicio("progreso")
    sid = _sesion_sintetica(bd, alumno, 1)
    _prediccion(bd, alumno, sid, "zzzz-sint-v1")
    for n in range(2, 6):
        _sesion_real(bd, alumno, n)
    with SessionLocal() as db:
        prediccion.guardar(db, alumno)
    todas = cliente.get("/predicciones", params={"student_id": alumno}).json()
    assert sorted({p["modelo_version"] for p in todas}) == ["rf-vent4-sinDET-test", "zzzz-sint-v1"]
    reales = cliente.get("/predicciones", params={"student_id": alumno, "origen": "real"}).json()
    sint = cliente.get("/predicciones", params={"student_id": alumno, "origen": "sintetico"}).json()
    assert [p["modelo_version"] for p in reales] == ["rf-vent4-sinDET-test"] and len(sint) == 1
    assert cliente.get("/predicciones", params={"origen": "otro"}).status_code == 422
    assert cliente.get("/resumen").json()["ultima_version_modelo"] != "rf-vent4-sinDET-test"


# ------------------------------------------------------------------------------------------------ cierre de sesión y correcciones
def test_al_cerrar_una_sesion_real_se_predice_sin_romper_la_conversacion(cliente, alumno, fake, bd, modelo_servicio):
    modelo_servicio("progreso")
    for n in range(1, 4):
        _sesion_real(bd, alumno, n, amlu=3.0)
    cid = _terminar_con(cliente, fake, alumno, (2, 2, 2, 2, 2))
    estado = cliente.get(f"/conversaciones/{cid}").json()["estado"]
    assert estado == "terminada"
    d = cliente.get(f"/students/{alumno}/prediccion").json()
    assert [p["sesion_num"] for p in d["predicciones"]] == [4] and d["predicciones"][0]["etiqueta_predicha"] == "progreso"


def test_si_la_prediccion_falla_la_sesion_se_cierra_igual(cliente, alumno, fake, bd, monkeypatch):
    def rompe(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(prediccion, "guardar", rompe)
    cid = _terminar_con(cliente, fake, alumno, ())
    assert cliente.get(f"/conversaciones/{cid}").json()["estado"] == "terminada"
    assert len(cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()) == 1


def test_las_conversaciones_de_prueba_no_generan_prediccion(cliente, alumno, fake, bd, modelo_servicio, monkeypatch):
    llamadas = []
    monkeypatch.setattr(prediccion, "guardar_sin_romper", lambda db, a: llamadas.append(a))
    cid = crear(cliente, alumno, prueba=True)["conversacion_id"]
    turno(cliente, cid, "hola"); turno(cliente, cid, "sí")
    for _ in range(20):
        fake.respuestas = [2]
        if turno(cliente, cid, "¿qué quiere decir eso?").json()["estado"] == "terminada":
            break
    assert cliente.get(f"/conversaciones/{cid}").json()["estado"] == "terminada"
    assert llamadas == [] and cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json() == []


def test_train_classifier_deja_el_modelo_de_servicio_en_el_joblib_del_modelo_entrenado():
    """El joblib que escribe `make train` ya trae el bloque `servicio` válido (si se ha entrenado en esta máquina)."""
    ruta = prediccion.RUTA
    if not ruta.exists():
        pytest.skip("sin src/models/classifier.joblib: ejecuta `make train`")
    servicio, motivo = prediccion._validar(joblib.load(ruta))
    assert servicio is not None, motivo
