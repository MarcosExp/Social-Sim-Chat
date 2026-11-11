"""nivel_ruido (ER v2, student_profile_sim): la carga del corpus de Marcos lo recoge si el generador lo trae y no mueve el
corpus. Acuerdo del 25/10/2026: lo añade Marcos al generador (Deixis «alto», el resto «medio»); aquí solo se prueba la carga.
Las pruebas no dependen de que el generador ya lo tenga: se lo ponen o se lo quitan con un adaptador."""
import pandas as pd
import pytest

from generador import generador_corpus_sintetico as gen
from scripts import seed_corpus

NIVEL = {"Deixis": "alto"}


def con_generador(monkeypatch, nivel_ruido):
    """Sustituye generar_corpus por uno que devuelve el mismo corpus con la columna `nivel_ruido` (función de la
    competencia), sin ella (None) o con la que se pase (callable)."""
    original = gen.generar_corpus

    def adaptado(cfg, seed=None):
        train, meta = original(cfg, seed)
        meta = meta.drop(columns=["nivel_ruido"], errors="ignore")
        if nivel_ruido == "regla":
            meta = meta.assign(nivel_ruido=meta["competencia"].map(lambda c: NIVEL.get(c, "medio")))
        elif callable(nivel_ruido):
            meta = meta.assign(nivel_ruido=nivel_ruido(meta))
        return train, meta

    monkeypatch.setattr(gen, "generar_corpus", adaptado)


def test_la_carga_recoge_nivel_ruido_cuando_el_generador_lo_trae(monkeypatch):
    con_generador(monkeypatch, "regla")
    perfiles, _ = seed_corpus.corpus_marcos(None)
    por_competencia = perfiles.groupby("competencia_objetivo")["nivel_ruido"].agg(lambda x: sorted(set(x))).to_dict()
    assert por_competencia == {"Deixis": ["alto"], "Metáfora": ["medio"], "Preguntas recíprocas": ["medio"],
                               "Sarcasmo": ["medio"]}


def test_sin_la_columna_no_se_inventa_ningun_valor(monkeypatch):
    con_generador(monkeypatch, None)
    perfiles, _ = seed_corpus.corpus_marcos(None)
    assert "nivel_ruido" not in perfiles.columns   # seed() lo deja en NULL


def test_anadir_nivel_ruido_no_mueve_el_corpus(monkeypatch):
    con_generador(monkeypatch, None)
    perfiles_sin, sesiones_sin = seed_corpus.corpus_marcos(7)
    con_generador(monkeypatch, "regla")
    perfiles_con, sesiones_con = seed_corpus.corpus_marcos(7)
    pd.testing.assert_frame_equal(sesiones_sin, sesiones_con)                               # sesiones: idénticas
    pd.testing.assert_frame_equal(perfiles_sin, perfiles_con.drop(columns=["nivel_ruido"]))  # perfiles: salvo la columna


@pytest.mark.parametrize("valor", ["Alto", "alta", "", "medio "])
def test_un_valor_fuera_de_bajo_medio_alto_se_rechaza(monkeypatch, valor):
    con_generador(monkeypatch, lambda meta: valor)
    with pytest.raises(ValueError, match="nivel_ruido solo admite"):
        seed_corpus.corpus_marcos(None)
