"""ER v2 (migración 008): una sola tabla de sesiones con `origen`, nombres en minúsculas, etiquetas sin tilde y los campos
del ER en los turnos. Incluye el control ANTIFUGA: las sesiones reales no entran en el entrenamiento."""
from types import SimpleNamespace as T

import pytest
from sqlalchemy import text

from app import metricas
from tests.test_api_conversacion import crear, turno


def terminar_conversacion(cliente, fake, alumno, evaluaciones=(2, 2, 2, 2)):
    cid = crear(cliente, alumno)["conversacion_id"]
    turno(cliente, cid, "hola"); turno(cliente, cid, "sí")
    for ev in evaluaciones:
        fake.respuestas = [ev]
        r = turno(cliente, cid, "¿qué quiere decir eso?" if ev == 2 else "no sé").json()
    assert r["estado"] == "terminada"
    return cid


def test_columnas_del_er_en_minusculas_y_sin_session_real(bd):
    with bd.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'session_data'"))}
        perfil = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'student_profile_sim'"))}
        turno_cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'conversacion_turno'"))}
        session_real = c.execute(text("SELECT to_regclass('session_real')")).scalar()
    assert {"amlu", "irc_pct", "pepe", "pct_det", "pct_det_observado_en_turnos"} <= cols
    assert not ({"aMLU", "IRC_pct", "PEPE", "pct_DET"} & cols)
    assert {"fecha", "personaje", "etiqueta_corregida", "nota_clinica", "origen", "conversacion_id"} <= cols
    assert {"sesion_inicio_evento", "arquetipo", "nivel_ruido"} <= perfil and "inicio_cambio" not in perfil
    assert {"iniciativa", "accuracy_corregido", "ayudas_solicitadas"} <= turno_cols
    assert session_real is None, "session_real debe haber desaparecido (migración 008)"


def test_sesion_real_va_a_session_data_con_origen_real(cliente, alumno, fake, bd):
    cid = terminar_conversacion(cliente, fake, alumno)
    with bd.connect() as c:
        f = c.execute(text("SELECT origen, conversacion_id::text AS cid, etiqueta_real_disenada, personaje, fecha, "
                           "sesion_num FROM session_data WHERE student_id = :s"), {"s": alumno}).mappings().one()
    assert f["origen"] == "real" and f["cid"] == cid and f["etiqueta_real_disenada"] is None
    assert f["personaje"] and f["fecha"] is not None and f["sesion_num"] == 1


def test_la_numeracion_real_continua_la_sintetica(cliente, alumno, fake, bd):
    with bd.begin() as c:
        for n in (1, 2, 3):
            c.execute(text(
                "INSERT INTO session_data (session_id, student_id, sesion_num, competencia, origen, amlu, "
                "latencia_pragmatica_ms, irc_pct, pepe, pct_det, etiqueta_real_disenada) "
                "VALUES (gen_random_uuid(), :s, :n, 'Metáfora', 'sintetico', 3, 4000, 20, 1, 50, 'progreso')"),
                {"s": alumno, "n": n})
    terminar_conversacion(cliente, fake, alumno)
    with bd.connect() as c:
        n = c.execute(text("SELECT sesion_num FROM session_data WHERE student_id = :s AND origen = 'real'"),
                      {"s": alumno}).scalar()
    assert n == 4                                         # UNIQUE (student_id, sesion_num) del ER


def test_restricciones_de_origen_y_etiquetas(bd, alumno):
    import sqlalchemy.exc as sx
    base = ("INSERT INTO session_data (session_id, student_id, sesion_num, competencia, origen, etiqueta_real_disenada) "
            "VALUES (gen_random_uuid(), :s, :n, 'Metáfora', :o, :e)")
    with pytest.raises(sx.IntegrityError):               # real sin conversacion_id
        with bd.begin() as c:
            c.execute(text(base), {"s": alumno, "n": 1, "o": "real", "e": None})
    with pytest.raises(sx.IntegrityError):               # sintética sin etiqueta de diseño
        with bd.begin() as c:
            c.execute(text(base), {"s": alumno, "n": 2, "o": "sintetico", "e": None})
    with pytest.raises(sx.IntegrityError):               # etiqueta con tilde/mayúscula (el ER v2 las guarda sin ellas)
        with bd.begin() as c:
            c.execute(text(base), {"s": alumno, "n": 3, "o": "sintetico", "e": "Regresión"})


def test_el_entrenamiento_no_lee_sesiones_reales(cliente, alumno, fake, bd):
    """ANTIFUGA: una sesión real (sin etiqueta) nunca llega a la tabla de entrenamiento."""
    from scripts import train_classifier
    terminar_conversacion(cliente, fake, alumno)
    ses, _ = train_classifier.cargar()
    assert alumno not in set(ses["alumno_id"])


def test_turno_guarda_iniciativa_y_ayudas(cliente, alumno, fake, bd):
    cid = terminar_conversacion(cliente, fake, alumno, evaluaciones=(0, 2, 2, 2, 2))   # M1: 0 -> ayuda -> 2
    with bd.connect() as c:
        filas = c.execute(text(
            "SELECT intento, texto, iniciativa, ayudas_solicitadas, tipo FROM conversacion_turno "
            "WHERE conversacion_id = CAST(:c AS UUID) AND rol = 'menor' ORDER BY orden"), {"c": cid}).mappings().all()
    comp = [f for f in filas if f["tipo"] == "competencia"]
    assert all(f["iniciativa"] is not None for f in filas)
    assert comp[0]["ayudas_solicitadas"] == 0 and comp[1]["intento"] == 2 and comp[1]["ayudas_solicitadas"] == 1
    assert any(f["iniciativa"] for f in comp if "?" in f["texto"])


def t(rol, tipo, texto, evaluacion=None, intento=1, rama=None, latencia_ms=None, nodo=None, accuracy_corregido=None):
    return T(rol=rol, tipo=tipo, texto=texto, evaluacion=evaluacion, intento=intento, rama=rama, latencia_ms=latencia_ms,
             nodo=nodo, accuracy_corregido=accuracy_corregido)


def test_las_metricas_usan_la_valoracion_corregida():
    """ER: efectivo = COALESCE(accuracy_corregido, accuracy_score). El terapeuta corrige un 0 del LLM a 2."""
    sin = [t("menor", "competencia", "una forma de hablar", evaluacion=0, nodo="M1")]
    con = [t("menor", "competencia", "una forma de hablar", evaluacion=0, nodo="M1", accuracy_corregido=2)]
    assert metricas.calcular(sin).PEPE == 0.0 and metricas.calcular(sin).aMLU is None
    assert metricas.calcular(con).PEPE == 2.0 and metricas.calcular(con).aMLU == 4.0
    assert metricas.evaluacion_efectiva(con[0]) == 2 and con[0].evaluacion == 0       # el original se conserva


# --- ADR-002 / migración 009: vista `turn_data` (una fila por figura sobre los intentos) -------------------------------

def _terminar_con(cliente, fake, alumno, secuencia):
    """Conduce la conversación hasta cerrarla: cada turno de competencia recibe la siguiente valoración (después, 2)."""
    cid = crear(cliente, alumno)["conversacion_id"]
    turno(cliente, cid, "hola"); turno(cliente, cid, "sí")
    cola = list(secuencia)
    for _ in range(20):
        ev = cola.pop(0) if cola else 2
        fake.respuestas = [ev]
        r = turno(cliente, cid, "¿qué quiere decir eso?" if ev == 2 else "no sé").json()
        if r["estado"] == "terminada":
            return cid
    raise AssertionError("la conversación no terminó")


def _vista(bd, cid):
    with bd.connect() as c:
        return c.execute(text(
            "SELECT * FROM turn_data WHERE conversacion_id = CAST(:c AS UUID) ORDER BY turno_num"), {"c": cid}).mappings().all()


def test_vista_turn_data_una_fila_por_figura_y_regla_2_1_0(cliente, alumno, fake, bd):
    # M1: 0 -> ayuda -> 2 (=1) · resto a la primera (=2)
    cid = _terminar_con(cliente, fake, alumno, (0, 2, 2, 2, 2))
    filas = _vista(bd, cid)
    comp = [f for f in filas if f["tipo"] == "competencia"]
    with bd.connect() as c:
        intentos = c.execute(text("SELECT count(*) FROM conversacion_turno WHERE conversacion_id = CAST(:c AS UUID) "
                                  "AND rol = 'menor' AND tipo = 'competencia'"), {"c": cid}).scalar()
    assert len(comp) == len({f["figura"] for f in comp}) == intentos - 1          # un reintento -> una fila menos
    assert [f["accuracy_score"] for f in comp][0] == 1 and comp[0]["ayudas_solicitadas"] == 1 and comp[0]["n_intentos"] == 2
    assert all(f["accuracy_score"] == 2 and f["ayudas_solicitadas"] == 0 for f in comp[1:])
    assert all(f["accuracy_corregido"] is None for f in comp)                      # nadie ha corregido nada
    assert [f["turno_num"] for f in filas] == list(range(1, len(filas) + 1))
    assert all(f["es_prueba"] is False and f["session_id"] is not None for f in filas)
    assert all(f["accuracy_score"] is None for f in filas if f["tipo"] != "competencia")   # la apertura no se puntúa


def test_vista_coincide_con_pepe_de_session_data(cliente, alumno, fake, bd):
    cid = _terminar_con(cliente, fake, alumno, (0, 2, 0, 0, 2))
    scores = [f["accuracy_efectivo"] for f in _vista(bd, cid) if f["accuracy_efectivo"] is not None]
    with bd.connect() as c:
        r = c.execute(text("SELECT pepe, n_figuras FROM session_data WHERE conversacion_id = CAST(:c AS UUID)"),
                      {"c": cid}).mappings().one()
    assert len(scores) == r["n_figuras"]
    assert round(sum(scores) / len(scores), 2) == float(r["pepe"])                 # la vista y PEPE usan la misma regla


def test_vista_refleja_la_correccion_del_terapeuta(cliente, alumno, fake, bd):
    cid = _terminar_con(cliente, fake, alumno, (0, 0, 0, 0))   # fallos sin ayuda eficaz
    with bd.begin() as c:
        c.execute(text(
            "UPDATE conversacion_turno SET accuracy_corregido = 2 WHERE id = ("
            "SELECT id FROM conversacion_turno WHERE conversacion_id = CAST(:c AS UUID) AND rol = 'menor' "
            "AND tipo = 'competencia' AND intento = 1 ORDER BY orden LIMIT 1)"), {"c": cid})
    primera = [f for f in _vista(bd, cid) if f["tipo"] == "competencia"][0]
    assert primera["accuracy_score"] == 0 and primera["accuracy_corregido"] == 2 and primera["accuracy_efectivo"] == 2
