#!/usr/bin/env python3
"""Entrena el clasificador propio (Progreso / Estancamiento / Regresión).

Pieza de IA SEPARADA del LLM: el LLM solo genera la conversación; este modelo
clasifica la trayectoria del alumno a partir de sus métricas.

Reutiliza SIN modificar el código de Marcos (PR #2): features de ventana
(`ml/features.py`: 15 features sobre las últimas 4 sesiones) y funciones de
validación (`ml/evaluar_corpus.py`: RandomForest, StratifiedGroupKFold por
alumno, modelo tramposo, etiquetas permutadas, heurística, retraso de detección).

Flujo:
  1. Lee `session_data` + `student_profile_sim` de Postgres.
  2. Validación cruzada por alumno -> métricas y predicciones fuera de fold.
  3. Comprobaciones anti-fuga y comparación con la heurística de referencia.
  4. Ajusta el modelo final con todo el corpus y lo guarda en models/.
  5. Escribe las predicciones (sesiones con ventana completa, >= 4) en
     `classifier_predictions`.

Uso:
    python -m scripts.train_classifier
    python -m scripts.train_classifier --no-db     # solo entrena y mide

Una sola ejecución = una sola partición en folds; Marcos promedia 10 semillas
(`python ml/evaluar_corpus.py`), así que cada métrica aquí oscila ~±0.05.
Datos SINTÉTICOS: validan la arquitectura, no la eficacia clínica.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix

from app import ml_config
from app.ml_config import construir_features, heuristica
from ml.evaluar_corpus import CLASES, cv_predict, metricas, retraso_deteccion, rf

COLUMNAS_FEATURES = ml_config.columnas_features()
VENTANA = ml_config.ventana()

# Umbrales de éxito (recall de estancamiento revisado a >=0.65 tras medir el efecto de las transiciones).
UMBRALES = {"f1_macro": 0.75, "recall_estancamiento": 0.65, "precision_estancamiento": 0.65}
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
# La BD guarda las etiquetas en minúsculas y sin tilde (ER v2); SIN_ACENTO acepta además las formas con mayúscula/tilde.
SIN_ACENTO = {"Progreso": "progreso", "Estancamiento": "estancamiento", "Regresión": "regresion",
              "progreso": "progreso", "estancamiento": "estancamiento", "regresion": "regresion"}
CON_ACENTO = {"progreso": "Progreso", "estancamiento": "Estancamiento", "regresion": "Regresión"}   # solo para informes


def cargar() -> tuple[pd.DataFrame, pd.DataFrame]:
    from sqlalchemy import text

    from app.db import engine

    q_ses = text(
        'SELECT student_id AS alumno_id, sesion_num AS sesion, session_id::text AS session_id, competencia, '
        'amlu AS "aMLU", latencia_pragmatica_ms, irc_pct AS "IRC_pct", pepe AS "PEPE", pct_det AS "pct_DET", '
        "etiqueta_real_disenada "
        # ANTIFUGA: el entrenamiento solo usa el corpus sintético; las sesiones reales no tienen etiqueta ni deben mezclarse.
        "FROM session_data WHERE origen = 'sintetico' ORDER BY student_id, sesion_num"
    )
    q_meta = text(
        "SELECT student_id AS alumno_id, competencia_objetivo AS competencia, trayectoria_disenada, "
        "sesion_inicio_evento AS inicio_cambio, ambiguo FROM student_profile_sim"
    )
    with engine.connect() as c:
        ses, meta = pd.read_sql(q_ses, c), pd.read_sql(q_meta, c)
    for col in ["aMLU", "latencia_pragmatica_ms", "IRC_pct", "PEPE", "pct_DET"]:
        ses[col] = ses[col].astype(float)
    ses["etiqueta"] = ses["etiqueta_real_disenada"].map(lambda e: SIN_ACENTO[e.split(" (")[0].strip()])
    meta["trayectoria"] = meta["trayectoria_disenada"].map(lambda e: SIN_ACENTO[e.split(" (")[0].strip()])
    return ses, meta


def proba_oof(X: np.ndarray, y: np.ndarray, fold: np.ndarray, seed: int) -> np.ndarray:
    """Probabilidades fuera de fold con los MISMOS folds que cv_predict (mismas predicciones)."""
    P = np.zeros((len(y), len(CLASES)))
    for k in np.unique(fold):
        tr, te = fold != k, fold == k
        m = rf(seed).fit(X[tr], y[tr])
        P[np.ix_(te, [CLASES.index(c) for c in m.classes_])] = m.predict_proba(X[te])
    return P


def alerta_operacional(F: pd.DataFrame, pred: np.ndarray) -> np.ndarray:
    """3 sesiones consecutivas predichas como no-progreso (misma regla que `retraso_deteccion`)."""
    d = F[["alumno_id", "sesion"]].copy()
    d["np"] = pred != "progreso"
    r = d.sort_values(["alumno_id", "sesion"]).groupby("alumno_id")["np"].transform(
        lambda s: s.rolling(3).sum() == 3
    )
    return r.reindex(d.index).fillna(False).to_numpy()


def guardar_predicciones(F, pred, proba, alerta, version) -> int:
    from sqlalchemy import text

    from app.db import engine

    filas = [
        {"student_id": F["alumno_id"].iat[i], "session_id": F["session_id"].iat[i], "v": version,
         "e": pred[i], "c": round(float(proba[i].max()), 3), "a": bool(alerta[i])}
        for i in range(len(F))
    ]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM classifier_predictions WHERE modelo_version = :v"), {"v": version})
        conn.execute(
            text(
                "INSERT INTO classifier_predictions (student_id, session_id, modelo_version, etiqueta_predicha, "
                "confianza, es_estancamiento_operacional) "
                "VALUES (:student_id, CAST(:session_id AS UUID), :v, :e, :c, :a)"
            ),
            filas,
        )
        # Última predicción también en session_data (campos del ER entregado); el historial queda en classifier_predictions.
        conn.execute(text("UPDATE session_data SET etiqueta_prediccion = NULL, confianza_prediccion = NULL "
                          "WHERE origen = 'sintetico'"))
        conn.execute(
            text("UPDATE session_data SET etiqueta_prediccion = :e, confianza_prediccion = :c "
                 "WHERE session_id = CAST(:session_id AS UUID)"),
            filas,
        )
    return len(filas)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-db", action="store_true", help="No escribe predicciones en Postgres")
    args = ap.parse_args()

    ses, meta = cargar()
    if ses.empty:
        print("session_data está vacío: ejecuta antes `make seed`.")
        return 2

    F = construir_features(ses)
    y = F["etiqueta"].to_numpy(dtype=object)
    g = F["alumno_id"].to_numpy()
    X = F[COLUMNAS_FEATURES].to_numpy()

    pred, fold, imp = cv_predict(X, y, g, args.seed)
    real = metricas(y, pred)
    proba = proba_oof(X, y, fold, args.seed)

    # anti-fuga 1: modelo tramposo (solo competencia + nº de sesión); 2: etiquetas permutadas; 3: heurística
    Xt = pd.get_dummies(F[["competencia"]]).assign(sesion=F["sesion"]).to_numpy(dtype=float)
    tramposo = metricas(y, cv_predict(Xt, y, g, args.seed)[0])
    yp = np.random.default_rng(args.seed).permutation(y)
    permutadas = metricas(y, cv_predict(X, y, g, args.seed, y_train=yp)[0])
    heur = metricas(y, heuristica(F))
    deteccion = None
    if meta["inicio_cambio"].notna().all():  # solo el corpus de Marcos trae el inicio del cambio
        deteccion = retraso_deteccion(F, pred, meta.assign(inicio_cambio=meta["inicio_cambio"].astype(int),
                                                           ambiguo=meta["ambiguo"].astype(bool)))

    version = f"rf-vent{VENTANA}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    r3 = lambda v: round(float(v), 3)  # noqa: E731
    out = {
        "modelo_version": version,
        "entrenado_en": datetime.now(timezone.utc).isoformat(),
        "n_alumnos": int(F["alumno_id"].nunique()),
        "n_sesiones": int(len(F)),
        "nota_sesiones": f"Sesiones 1-{VENTANA - 1} de cada alumno quedan fuera (sin ventana completa).",
        "features": COLUMNAS_FEATURES,
        "f1_macro": r3(real["f1_macro"]),
        "accuracy": r3(real["accuracy"]),
        "recall_estancamiento": r3(real["recall_estancamiento"]),
        "precision_estancamiento": r3(real["precision_estancamiento"]),
        "umbrales": UMBRALES,
        "matriz_confusion": {"etiquetas": [CON_ACENTO[c] for c in CLASES],
                             "valores": confusion_matrix(y, pred, labels=CLASES).tolist()},
        "heuristica": {"f1_macro": r3(heur["f1_macro"]), "recall_estancamiento": r3(heur["recall_estancamiento"])},
        "deteccion": {k: (None if pd.isna(v) else r3(v)) for k, v in deteccion.items()} if deteccion else None,
        "importancia_features": {c: r3(v) for c, v in sorted(zip(COLUMNAS_FEATURES, imp), key=lambda t: -t[1])[:8]},
        "aviso": "Datos sintéticos: valida la arquitectura, no la eficacia clínica. Una sola partición en folds (±0.05).",
    }
    out["cumple_umbrales"] = {k: bool(out[k] >= v) for k, v in UMBRALES.items()}
    out["anti_fuga"] = {
        "f1_macro_senuelo_competencia_sesion": r3(tramposo["f1_macro"]),
        "f1_macro_etiquetas_permutadas": r3(permutadas["f1_macro"]),
        "superado": bool(tramposo["f1_macro"] < real["f1_macro"] - 0.10 and permutadas["f1_macro"] < 0.45),
    }

    final = rf(args.seed).fit(X, y)  # modelo final: todo el corpus (para inferencia futura desde FastAPI)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"modelo": final, "features": COLUMNAS_FEATURES, "version": version, "ventana": VENTANA},
                MODELS_DIR / "classifier.joblib")
    if not args.no_db:
        out["predicciones_guardadas"] = guardar_predicciones(F, pred, proba, alerta_operacional(F, pred), version)
    (MODELS_DIR / "metrics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({k: out[k] for k in ("f1_macro", "accuracy", "recall_estancamiento", "precision_estancamiento",
                                         "cumple_umbrales", "anti_fuga", "heuristica", "deteccion")},
                     ensure_ascii=False, indent=2))
    print(f"Modelo {version} guardado en {MODELS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
