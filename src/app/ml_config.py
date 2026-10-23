"""Adaptador entre el código de Marcos (`src/ml/`, sin modificar) y el resto del sistema.

`ml/features.py` lee la ventana, la línea base y los rangos de la config del generador (`src/generador/config.yaml`,
bloque `features` y `metricas.<m>.rango`). Aquí se resuelve esa ruta una vez y se exponen los valores que usan el backend
y los scripts, para que entrenamiento e inferencia lean lo mismo. Las importaciones de `ml.*` son diferidas: arrastran
pandas/numpy.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "generador" / "config.yaml"


@lru_cache(maxsize=1)
def parametros() -> dict:
    from ml.features import cargar_parametros
    return cargar_parametros(CONFIG)


def ventana() -> int:
    return parametros()["ventana"]


def columnas_features() -> list[str]:
    from ml.features import columnas_features
    return columnas_features(CONFIG)


def construir_features(df):
    from ml.features import construir_features
    return construir_features(df, CONFIG)


def heuristica(F):
    from ml.evaluar_corpus import heuristica
    return heuristica(F, CONFIG)
