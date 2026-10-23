"""Regresión del prompt de valoración 0/1/2. La comprobación de datos corre siempre; la de Ollama REAL no corre por defecto:

    python -m pytest -m humo -s tests/test_bateria_valoracion.py
    (o sin pytest: python -m scripts.bateria_valoracion --detalle)

Datos en tests/data/bateria_valoracion_{1,2}.json. Los umbrales están en scripts/bateria_valoracion.py.
"""
import json
import sys

import pytest


def test_datos_de_las_baterias_son_coherentes():
    from scripts import bateria_valoracion as b
    from app.guiones import cargar_guiones
    ids = {t.id for g in cargar_guiones().competencias.values() for t in g.turnos}
    for n, esperado in (("1", 88), ("2", 100), ("3", 100)):
        casos = b.cargar(n)
        assert len(casos) >= esperado
        assert all(c["nodo"] in ids and c["respuesta"].strip() and set(c["esperado"]) <= {0, 1, 2} for c in casos)
        assert len({json.dumps([c["nodo"], c["respuesta"]]) for c in casos}) == len(casos)   # sin duplicados


@pytest.mark.humo
def test_prompt_de_valoracion_no_empeora_con_ollama_real():
    from scripts import bateria_valoracion
    sys.argv = ["bateria", "--historial", "con"]
    assert bateria_valoracion.main() == 0
