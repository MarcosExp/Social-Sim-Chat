#!/usr/bin/env python3
"""Variación del clasificador con la semilla, con y sin %DET. NO guarda modelo ni escribe en la BD.

    python -m scripts.semillas_clasificador                  # 5 semillas, corpus de la BD
    python -m scripts.semillas_clasificador --semillas 10 --corpus-nuevo

Mide cuánto se mueve el recall de estancamiento (umbral 0,65), el F1 macro y la precisión al cambiar solo la semilla:
  A) Corpus FIJO (el de la BD): cambia la partición en folds y el RandomForest.
  B) --corpus-nuevo: además regenera el corpus con el generador de Marcos para cada semilla (como `ml/evaluar_corpus.py`).
Variante «sin %DET»: se quitan sus 3 features (media, pendiente, dif_base), porque %DET real aún no se calcula como RQA
(docs/metricas-reales.md). Los mismos folds/semilla se usan con y sin %DET (comparación emparejada).
Datos SINTÉTICOS: valida la arquitectura, no la eficacia clínica.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ml.evaluar_corpus import cv_predict, metricas
from ml.features import COLUMNAS_FEATURES, construir_features

UMBRAL_RECALL = 0.65
CLAVES = ["recall_estancamiento", "f1_macro", "precision_estancamiento", "accuracy"]
CONFIGS = {"con %DET": COLUMNAS_FEATURES,
           "sin %DET": [c for c in COLUMNAS_FEATURES if not c.startswith("pct_DET")]}


def evaluar(F, seed: int) -> dict[str, dict]:
    y = F["etiqueta"].to_numpy(dtype=object)
    g = F["alumno_id"].to_numpy()
    out = {}
    for nombre, cols in CONFIGS.items():
        pred, _, _ = cv_predict(F[cols].to_numpy(), y, g, seed)
        m = metricas(y, pred)
        out[nombre] = {k: float(m[k]) for k in CLAVES}
    return out


def corpus_bd():
    from scripts.train_classifier import cargar
    ses, _ = cargar()
    return construir_features(ses)


def corpus_generado(seed: int):
    from generador.generador_corpus_sintetico import cargar_config, generar_corpus
    cfg = cargar_config(Path(__file__).resolve().parent.parent / "generador" / "config.yaml")
    train, _ = generar_corpus(cfg, seed)
    return construir_features(train), cfg["seed"]


def resumir(titulo: str, filas: dict[int, dict[str, dict]]) -> dict:
    print(f"\n=== {titulo} ===")
    resumen = {}
    for nombre in CONFIGS:
        print(f"\n  {nombre}  ({len(CONFIGS[nombre])} features)")
        print(f"  {'semilla':>8}" + "".join(f"{k:>26}" for k in CLAVES))
        for s, r in filas.items():
            print(f"  {s:>8}" + "".join(f"{r[nombre][k]:>26.3f}" for k in CLAVES))
        resumen[nombre] = {}
        for k in CLAVES:
            v = np.array([r[nombre][k] for r in filas.values()])
            resumen[nombre][k] = {"media": round(float(v.mean()), 3), "min": round(float(v.min()), 3),
                                  "max": round(float(v.max()), 3), "desv": round(float(v.std(ddof=1)), 3) if len(v) > 1 else 0.0}
        rec = np.array([r[nombre]["recall_estancamiento"] for r in filas.values()])
        resumen[nombre]["semillas_con_recall_>=_0.65"] = f"{int((rec >= UMBRAL_RECALL).sum())}/{len(rec)}"
        print(f"  {'media':>8}" + "".join(f"{resumen[nombre][k]['media']:>26.3f}" for k in CLAVES))
        print(f"  {'rango':>8}" + "".join(f"{str([resumen[nombre][k]['min'], resumen[nombre][k]['max']]):>26}" for k in CLAVES))
        print(f"  recall >= {UMBRAL_RECALL}: {resumen[nombre]['semillas_con_recall_>=_0.65']} semillas")
    d = {k: round(float(np.mean([r['sin %DET'][k] - r['con %DET'][k] for r in filas.values()])), 3) for k in CLAVES}
    print(f"\n  Diferencia media (sin %DET − con %DET): {d}")
    resumen["diferencia_media_sin_menos_con"] = d
    return resumen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--semillas", type=int, default=5)
    ap.add_argument("--primera", type=int, default=1, help="primera semilla (las siguientes son consecutivas)")
    ap.add_argument("--corpus-nuevo", action="store_true", help="además, regenerar el corpus por semilla (B)")
    ap.add_argument("--json", dest="salida", help="guarda el resumen en este fichero")
    a = ap.parse_args()
    semillas = list(range(a.primera, a.primera + a.semillas))
    informe = {"semillas": semillas}

    F = corpus_bd()
    print(f"Corpus de la BD: {len(F)} sesiones con ventana completa, {F['alumno_id'].nunique()} alumnos.")
    informe["A_corpus_fijo"] = resumir("A) corpus fijo (BD); cambia partición en folds y RandomForest",
                                       {s: evaluar(F, s) for s in semillas})
    if a.corpus_nuevo:
        filas = {}
        for s in semillas:
            Fg, base = corpus_generado(s)
            filas[s] = evaluar(Fg, s)
        informe["B_corpus_regenerado"] = resumir("B) corpus regenerado por semilla (generador de Marcos)", filas)
    if a.salida:
        Path(a.salida).write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
