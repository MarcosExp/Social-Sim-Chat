"""Adaptador del código de Marcos (`src/ml/`, sin modificar): parámetros y agrupación de las features."""
import pandas as pd

from app import ml_config


def test_los_parametros_salen_de_la_config_del_generador():
    p = ml_config.parametros()
    assert ml_config.CONFIG.name == "config.yaml" and ml_config.CONFIG.exists()
    assert (p["ventana"], p["n_base"]) == (4, 3) and ml_config.ventana() == 4
    assert len(ml_config.columnas_features()) == 3 * len(p["metricas"]) == 15


def test_las_features_agrupan_por_alumno_y_competencia():
    """Un alumno con dos competencias no mezcla sesiones: 5 sesiones por competencia dan 2 filas con ventana 4 en cada una."""
    metricas = ml_config.parametros()["metricas"]
    filas = [{"alumno_id": "a1", "competencia": c, "sesion": s, **{m: float(s) for m in metricas}}
             for c in ("Metáfora", "Sarcasmo") for s in range(1, 6)]
    F = ml_config.construir_features(pd.DataFrame(filas))
    assert len(F) == 4 and sorted(F["sesion"]) == [4, 4, 5, 5]
    assert set(ml_config.columnas_features()) <= set(F.columns)
    assert not F[ml_config.columnas_features()].isna().any().any()
