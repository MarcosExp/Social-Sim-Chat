"""Features de ventana del clasificador (SOCIAL-SIM Chat).

Para cada métrica, con las últimas `ventana` sesiones (incluida la actual,
nunca futuras): media, pendiente normalizada por el rango típico y diferencia
respecto a la media de las `n_base` primeras sesiones. Con 5 métricas son 15
features. Las sesiones sin ventana completa (1-3) no se predicen.

Agrupación: por (alumno, competencia) cuando el DataFrame trae la columna
`competencia` (backend), y por alumno cuando no (corpus_train, donde cada
alumno tiene una sola competencia y la competencia no debe llegar al modelo).
La competencia solo agrupa: nunca es feature.

Ventana, línea base y rangos se leen de config.yaml. Esta misma función se usa
en entrenamiento y en inferencia.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

CONFIG_POR_DEFECTO = Path("config.yaml")
SUFIJOS = ("media", "pendiente", "dif_base")


def cargar_parametros(cfg: dict | str | Path | None = None) -> dict:
    """Devuelve {'metricas', 'rango', 'ventana', 'n_base'} a partir de la config."""
    if cfg is None or isinstance(cfg, (str, Path)):
        with open(cfg or CONFIG_POR_DEFECTO, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    metricas = list(cfg["metricas"])
    return {
        "metricas": metricas,
        "rango": {m: float(cfg["metricas"][m]["rango"]) for m in metricas},
        "ventana": int(cfg["features"]["ventana"]),
        "n_base": int(cfg["features"]["n_base"]),
    }


def columnas_features(cfg: dict | str | Path | None = None) -> list[str]:
    p = cargar_parametros(cfg)
    return [f"{m}_{s}" for m in p["metricas"] for s in SUFIJOS]


def pendiente_ventana(valores: np.ndarray) -> float:
    """Pendiente de la recta de mínimos cuadrados sobre puntos equiespaciados."""
    x = np.arange(len(valores)) - (len(valores) - 1) / 2
    return float((x * (valores - valores.mean())).sum() / (x ** 2).sum())


def construir_features(df: pd.DataFrame, cfg: dict | str | Path | None = None,
                       col_alumno: str = "alumno_id", col_sesion: str = "sesion",
                       col_competencia: str = "competencia") -> pd.DataFrame:
    """Una fila por sesión con ventana completa. Conserva las columnas de `df`
    (alumno, sesión, etiqueta si existe) y añade las features."""
    p = cargar_parametros(cfg)
    v, nb = p["ventana"], p["n_base"]
    claves = [col_alumno] + ([col_competencia] if col_competencia in df.columns else [])
    partes = []
    for _, g in df.sort_values(claves + [col_sesion]).groupby(claves, sort=False):
        g = g.copy()
        for m in p["metricas"]:
            s = g[m].astype(float) / p["rango"][m]
            media = s.rolling(v).mean()
            g[f"{m}_media"] = media
            g[f"{m}_pendiente"] = s.rolling(v).apply(pendiente_ventana, raw=True)
            g[f"{m}_dif_base"] = media - s.iloc[:nb].mean()
        partes.append(g.iloc[v - 1:])
    return pd.concat(partes, ignore_index=True)
