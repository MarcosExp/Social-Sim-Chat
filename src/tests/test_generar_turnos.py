"""Tests de generar_turnos.py: piezas sin base de datos y carga en la BD con el contrato de la migración 013."""
from pathlib import Path

import pytest

from app.guiones import cargar_guiones
from scripts import generar_turnos as gt

SRC = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def corpus():
    from generador.generador_corpus_sintetico import cargar_config, generar_corpus
    cfg = cargar_config(SRC / "generador" / "config.yaml")
    train, meta = generar_corpus(cfg, 42)
    conv, turnos = gt.generar(train, meta, 42)
    return train, meta, conv, turnos


def test_composicion_respeta_pepe():
    for pepe in (0.0, 0.35, 1.0, 1.4, 2.0):
        for n in (3, 4):
            n2, n1, n0 = gt.composicion_figuras(pepe, 50, n)
            assert n2 + n1 + n0 == n and 2 * n2 + n1 == round(pepe * n)


def test_una_conversacion_por_sesion_y_7875_eventos_por_figura(corpus):
    train, _, conv, turnos = corpus
    assert len(conv) == len(train) == 1500
    menor = turnos[turnos.rol == "menor"]
    assert menor.groupby(["conversacion_id", "nodo"]).ngroups == 7875        # NF2, sección 8


def test_estructura_como_el_chat_real(corpus):
    _, _, _, turnos = corpus
    assert not turnos.duplicated(["conversacion_id", "orden"]).any()
    comp = turnos[(turnos.rol == "menor") & (turnos.tipo == "competencia")]
    assert comp.intento.isin([1, 2]).all() and comp.evaluacion.isin([0, 1, 2]).all()
    assert (comp.ayudas_solicitadas == (comp.intento > 1).astype(int)).all()
    # un 2 en el intento 1 cierra la figura: no hay segundo intento
    primeros = comp[comp.intento == 1].set_index(["conversacion_id", "nodo"]).evaluacion
    segundos = comp[comp.intento == 2].set_index(["conversacion_id", "nodo"]).index
    assert not any(primeros.loc[i] == 2 for i in segundos)


def test_metricas_recalculadas_cerca_de_la_sesion(corpus):
    train, _, conv, turnos = corpus
    c = gt.comprobar(train, conv, turnos)
    assert (c.dif_LPP == 0).all()                                         # mediana fijada exactamente
    assert (c.dif_PEPE.abs() <= 0.5 / c.n_figuras + 0.011).all()          # límite de discretización (± redondeo a 2 decimales)
    assert c.dif_aMLU.abs().median() < 0.2


def test_misma_semilla_mismos_turnos(corpus):
    train, meta, _, turnos = corpus
    _, otra = gt.generar(train, meta, 42, cargar_guiones())
    assert otra.equals(turnos)


# --------------------------------------------------------------------------- base de datos (migración 013)
def _score(intentos):
    """Regla 2/1/0 de la vista turn_data a partir de las valoraciones por intento."""
    ev = dict(zip(intentos.intento, intentos.evaluacion))
    return 2 if ev.get(1) == 2 else 1 if ev.get(2) == 2 else 0


@pytest.fixture
def corpus_tst(bd, corpus):
    """Dos alumnos del corpus (competencias distintas) cargados como el seed, con id TST-; se borran al terminar."""
    import uuid

    from sqlalchemy import text

    from scripts.seed_corpus import etiqueta_db
    train, meta, _, _ = corpus
    elegidos = list(meta.groupby("competencia").head(1).alumno_id[:2])
    pref = f"TST-{uuid.uuid4().hex[:6]}"
    ren = {a: f"{pref}-{a.split('-')[-1]}" for a in elegidos}
    t = train[train.alumno_id.isin(elegidos)].assign(alumno_id=lambda d: d.alumno_id.map(ren))
    m = meta[meta.alumno_id.isin(elegidos)].assign(alumno_id=lambda d: d.alumno_id.map(ren))
    with bd.begin() as c:
        for r in m.itertuples(index=False):
            c.execute(text("INSERT INTO student_profile_sim (student_id, competencia_objetivo, trayectoria_disenada, n_sesiones) "
                           "VALUES (:s, :c, 'progreso', :n)"), {"s": r.alumno_id, "c": r.competencia,
                                                                 "n": int((t.alumno_id == r.alumno_id).sum())})
        comp = m.set_index("alumno_id").competencia
        for r in t.itertuples(index=False):
            c.execute(text(
                "INSERT INTO session_data (session_id, student_id, sesion_num, competencia, origen, amlu, latencia_pragmatica_ms, "
                "irc_pct, pepe, pct_det, etiqueta_real_disenada) VALUES (CAST(:id AS UUID), :s, :n, :c, 'sintetico', :amlu, "
                ":lpp, :irc, :pepe, :det, :e)"),
                {"id": str(uuid.uuid5(gt.NS, f"{r.alumno_id}-{r.sesion}")), "s": r.alumno_id, "n": int(r.sesion),
                 "c": comp[r.alumno_id], "amlu": float(r.aMLU), "lpp": float(r.latencia_pragmatica_ms), "irc": float(r.IRC_pct),
                 "pepe": float(r.PEPE), "det": float(r.pct_DET), "e": etiqueta_db(r.etiqueta)})
    yield t, m
    with bd.begin() as c:
        c.execute(text("DELETE FROM student_profile_sim WHERE student_id = ANY(:ids)"), {"ids": list(ren.values())})


def test_insertar_enlaza_cada_sesion_y_turn_data_cubre_las_figuras(bd, corpus_tst):
    from sqlalchemy import text
    t, m = corpus_tst
    conv, turnos = gt.generar(t, m, 42)
    with bd.begin() as c:
        assert gt.insertar(c, conv, turnos) == (len(conv), len(turnos), len(t))
    with bd.begin() as c:                                                   # idempotente: no duplica ni reenlaza
        assert gt.insertar(c, conv, turnos) == (len(conv), len(turnos), len(t))
    ids = list(conv.conversacion_id)
    with bd.connect() as c:
        enlaces = c.execute(text(
            "SELECT s.session_id::text, c.conversacion_id::text, c.origen, c.es_prueba, c.estado FROM session_data s "
            "JOIN conversacion c USING (conversacion_id) WHERE s.student_id = ANY(:a)"), {"a": list(m.alumno_id)}).all()
        vista = c.execute(text(
            "SELECT conversacion_id::text AS cid, figura, accuracy_score, session_id FROM turn_data "
            "WHERE conversacion_id = ANY(CAST(:ids AS UUID[])) AND tipo = 'competencia'"), {"ids": ids}).mappings().all()
        origenes_eval = {r[0] for r in c.execute(text(
            "SELECT DISTINCT evaluacion_origen FROM conversacion_turno WHERE conversacion_id = ANY(CAST(:ids AS UUID[])) "
            "AND evaluacion IS NOT NULL"), {"ids": ids})}
    assert {(s, cid) for s, cid, *_ in enlaces} == set(zip(conv.session_id, conv.conversacion_id))     # por session_id
    assert all(o == "sintetico" and p is True and e == "terminada" for *_, o, p, e in enlaces)
    assert origenes_eval == {"sintetico"}
    comp = turnos[(turnos.rol == "menor") & (turnos.tipo == "competencia")]
    esperado = {(cid, nodo): _score(g) for (cid, nodo), g in comp.groupby(["conversacion_id", "nodo"])}
    assert {(f["cid"], f["figura"]): f["accuracy_score"] for f in vista} == esperado
    assert all(f["session_id"] is not None for f in vista)


def test_metricas_reales_y_listados_no_ven_los_turnos_sinteticos(cliente, bd, corpus_tst):
    from sqlalchemy import text

    from scripts import metricas_reales, train_classifier
    t, m = corpus_tst
    conv, turnos = gt.generar(t, m, 42)
    with bd.begin() as c:
        gt.insertar(c, conv, turnos)
    metricas_reales.sincronizar(recalcular=True)
    with bd.connect() as c:
        origenes = {r[0] for r in c.execute(text("SELECT origen FROM session_data WHERE student_id = ANY(:a)"),
                                            {"a": list(m.alumno_id)})}
    assert origenes == {"sintetico"}                                       # no aparece ninguna sesión «real»
    listado = {x["conversacion_id"] for x in cliente.get("/conversaciones").json()}
    assert not listado & set(conv.conversacion_id)
    ses, _ = train_classifier.cargar()                                     # ANTIFUGA: el entrenamiento las sigue leyendo
    assert set(ses[ses.alumno_id.isin(m.alumno_id)].session_id.astype(str)) == set(conv.session_id)


def test_seed_corpus_llama_a_generar_turnos_salvo_con_sin_turnos(monkeypatch):
    import sys

    from scripts import seed_corpus
    llamadas = []
    monkeypatch.setattr(seed_corpus, "seed", lambda *a, **k: llamadas.append(k.get("turnos")))
    for argv, esperado in ((["seed_corpus"], True), (["seed_corpus", "--sin-turnos"], False)):
        monkeypatch.setattr(sys, "argv", argv)
        seed_corpus.main()
    assert llamadas == [True, False]
