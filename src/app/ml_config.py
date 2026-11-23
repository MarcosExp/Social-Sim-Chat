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


# ------------------------------------------------------------------------------------------------ modelo de servicio
# El modelo que predice sobre sesiones REALES no usa las métricas provisionales (hoy, %DET: `metricas.PROVISIONALES`).
# No se toca `ml/`: `cargar_parametros()` acepta un dict, así que aquí se le pasa la misma config sin esas métricas
# (acordado con Marcos, 19/11/2026). Entrenamiento del modelo de servicio e inferencia leen ESTA config.
SUFIJO_VERSION_SERVICIO = "sinDET"      # va en `modelo_version`: deja claro que el modelo no usa %DET


@lru_cache(maxsize=1)
def config_servicio() -> dict:
    import yaml

    from app.metricas import columnas_para_clasificador
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    permitidas = columnas_para_clasificador()
    return {"metricas": {m: v for m, v in cfg["metricas"].items() if m in permitidas}, "features": cfg["features"]}


def metricas_servicio() -> list[str]:
    return list(config_servicio()["metricas"])


def columnas_features_servicio() -> list[str]:
    from ml.features import columnas_features
    return columnas_features(config_servicio())


def construir_features_servicio(df):
    from ml.features import construir_features
    return construir_features(df, config_servicio())


def heuristica_servicio(F):
    from ml.evaluar_corpus import heuristica
    return heuristica(F, config_servicio())
