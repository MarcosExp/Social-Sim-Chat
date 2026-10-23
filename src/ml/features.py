"""Features de ventana (sección 1 de cambios-generador-corpus.md).

Para cada métrica, con las últimas 4 sesiones (incluida la actual, nunca
futuras): media, pendiente normalizada por el rango típico y diferencia
respecto a la media de las 3 primeras sesiones del alumno. 15 features.
Las sesiones 1-3 no tienen ventana completa y quedan fuera.

La misma función debe usarse en entrenamiento y en inferencia.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

METRICAS = ["aMLU", "latencia_pragmatica_ms", "IRC_pct", "PEPE", "pct_DET"]
RANGO = {"aMLU": 5, "latencia_pragmatica_ms": 5000, "IRC_pct": 100, "PEPE": 2, "pct_DET": 100}
VENTANA = 4
N_BASE = 3


def construir_features(df: pd.DataFrame, col_alumno: str = "alumno_id",
                       col_sesion: str = "sesion") -> pd.DataFrame:
    """Devuelve una fila por sesión con ventana completa. Conserva las columnas
    de `df` (alumno, sesión, etiqueta si existe) y añade las 15 features."""
    x = np.arange(VENTANA) - (VENTANA - 1) / 2
    denom = (x ** 2).sum()
    partes = []
    for _, g in df.sort_values([col_alumno, col_sesion]).groupby(col_alumno, sort=False):
        g = g.copy()
        for m in METRICAS:
            v = g[m].astype(float) / RANGO[m]
            base = v.iloc[:N_BASE].mean()
            media = v.rolling(VENTANA).mean()
            pend = v.rolling(VENTANA).apply(lambda w: float((x * (w - w.mean())).sum() / denom), raw=True)
            g[f"{m}_media"] = media
            g[f"{m}_pendiente"] = pend
            g[f"{m}_dif_base"] = media - base
        partes.append(g.iloc[VENTANA - 1:])
    return pd.concat(partes, ignore_index=True)


COLUMNAS_FEATURES = [f"{m}_{s}" for m in METRICAS for s in ("media", "pendiente", "dif_base")]
