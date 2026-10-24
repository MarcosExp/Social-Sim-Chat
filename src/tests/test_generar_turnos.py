"""Tests del borrador de generar_turnos.py (sin base de datos)."""
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
