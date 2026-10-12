"""Evaluación del corpus sintético y comprobaciones antifuga
(sección 7 de cambios-generador-corpus.md).

Validación cruzada por alumno (StratifiedGroupKFold, k=5), RandomForest con
class_weight="balanced". Se repite sobre varias semillas del generador.

Uso:
    python src/ml/evaluar_corpus.py --config config.yaml --semillas 10 \
        --barrido-ruido 0.01 0.02 0.03 0.05 0.07
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_recall_fscore_support)
from sklearn.model_selection import StratifiedGroupKFold

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "generador"))
sys.path.insert(0, str(RAIZ / "ml"))
from generador_corpus_sintetico import cargar_config, generar_corpus  # noqa: E402
from features import cargar_parametros, columnas_features, construir_features  # noqa: E402

CLASES = ["estancamiento", "progreso", "regresion"]


def rf(seed=0):
    return RandomForestClassifier(300, random_state=seed, class_weight="balanced",
                                  min_samples_leaf=2, n_jobs=-1)


def cv_predict(X, y, grupos, seed, y_train=None):
    """Predicción fuera de fold. `y` estratifica y evalúa; `y_train` (si se da)
    es con lo que se entrena (para la prueba de etiquetas permutadas)."""
    y_train = y if y_train is None else y_train
    pred = np.empty(len(y), dtype=object)
    fold = np.zeros(len(y), dtype=int)
    imp = []
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    for k, (tr, te) in enumerate(cv.split(X, y, grupos)):
        m = rf(seed).fit(X[tr], y_train[tr])
        pred[te] = m.predict(X[te])
        fold[te] = k
        imp.append(m.feature_importances_)
    return pred, fold, np.mean(imp, axis=0)


def heuristica(F, cfg):
    """Regla de referencia: pendiente de PEPE en la ventana (en PEPE por sesión).
    < -0,02 regresión; entre -0,02 y +0,02 estancamiento; > +0,02 progreso."""
    p = F["PEPE_pendiente"].to_numpy() * cargar_parametros(cfg)["rango"]["PEPE"]
    return np.where(p < -0.02, "regresion", np.where(p <= 0.02, "estancamiento", "progreso")).astype(object)


def metricas(y, p):
    pr, rc, f1, _ = precision_recall_fscore_support(y, p, labels=CLASES, zero_division=0)
    d = {"accuracy": accuracy_score(y, p), "f1_macro": f1_score(y, p, labels=CLASES, average="macro", zero_division=0)}
    for i, c in enumerate(CLASES):
        d[f"precision_{c}"], d[f"recall_{c}"], d[f"f1_{c}"] = pr[i], rc[i], f1[i]
    return d


def retraso_deteccion(F, pred, meta):
    """Alerta = 3 sesiones consecutivas predichas como no-progreso.
    Retraso = sesión en que salta la alerta − inicio_cambio (alumnos con cambio).
    Falsa alerta = alumno de trayectoria progreso con alguna alerta."""
    d = F[["alumno_id", "sesion"]].copy()
    d["no_prog"] = pred != "progreso"
    m = meta.set_index("alumno_id")
    retrasos, sin_detectar, falsas, n_prog = [], 0, 0, 0
    for a, g in d.groupby("alumno_id"):
        g = g.sort_values("sesion")
        racha = g["no_prog"].rolling(3).sum() == 3
        alertas = g.loc[racha, "sesion"]
        if m.loc[a, "trayectoria"] == "progreso":
            n_prog += 1
            falsas += int(len(alertas) > 0)
            continue
        ini = m.loc[a, "inicio_cambio"]
        validas = alertas[alertas >= ini]
        if len(validas):
            retrasos.append(int(validas.iloc[0] - ini))
        else:
            sin_detectar += 1
    n_cambio = len(retrasos) + sin_detectar
    return {"retraso_mediano": float(np.median(retrasos)) if retrasos else np.nan,
            "retraso_medio": float(np.mean(retrasos)) if retrasos else np.nan,
            "pct_alumnos_detectados": len(retrasos) / max(1, n_cambio),
            "pct_falsa_alerta_progreso": falsas / max(1, n_prog)}


def evaluar_semilla(cfg, seed, completo=True):
    train, meta = generar_corpus(cfg, seed)
    F = construir_features(train, cfg)
    y = F["etiqueta"].to_numpy(dtype=object)
    g = F["alumno_id"].to_numpy()
    X = F[columnas_features(cfg)].to_numpy()

    pred, fold, imp = cv_predict(X, y, g, seed)
    res = {"real": metricas(y, pred)}
    por_fold = [metricas(y[fold == k], pred[fold == k]) for k in range(5)]
    res["mayoritaria"] = float(pd.Series(y).value_counts(normalize=True).max())
    res["distribucion"] = pd.Series(train["etiqueta"]).value_counts(normalize=True).to_dict()
    if not completo:
        return res, por_fold, None, None

    # 1. modelo tramposo: solo competencia + nº de sesión
    Ft = F.merge(meta[["alumno_id", "competencia"]], on="alumno_id")
    Xt = pd.get_dummies(Ft[["competencia"]]).assign(sesion=Ft["sesion"]).to_numpy(dtype=float)
    pt, _, _ = cv_predict(Xt, y, g, seed)
    res["tramposo"] = metricas(y, pt)
    # 2. etiquetas permutadas (se entrena con etiquetas barajadas)
    yp = np.random.default_rng(seed).permutation(y)
    pp, _, _ = cv_predict(X, y, g, seed, y_train=yp)
    res["permutadas"] = metricas(y, pp)
    # referencia: heurística
    res["heuristica"] = metricas(y, heuristica(F, cfg))
    res["deteccion"] = retraso_deteccion(F, pred, meta)
    # desglose: sin ambiguos / cerca del inicio del cambio
    Fm = F.merge(meta, on="alumno_id")
    amb = Fm["ambiguo"].to_numpy()
    res["sin_ambiguos"] = metricas(y[~amb], pred[~amb])
    dist = (Fm["sesion"] - Fm["inicio_cambio"]).to_numpy()
    cambio = (Fm["trayectoria"] != "progreso").to_numpy()
    trans = cambio & (dist >= 0) & (dist <= 2)
    asent = cambio & (dist >= 3)
    res["acierto_transicion_0_2"] = float((pred[trans] == y[trans]).mean())
    res["acierto_asentado_3mas"] = float((pred[asent] == y[asent]).mean())
    cm = confusion_matrix(y, pred, labels=CLASES)
    return res, por_fold, imp, cm


# Umbrales cerrados (sección 8 del NF2 / cambios-generador-corpus.md)
UMBRALES = [
    # (nombre, función sobre el resultado de una semilla o fold -> bool)
    ("f1_macro >= 0.75", lambda r: r["real"]["f1_macro"] >= 0.75),
    ("precision_estancamiento >= 0.65", lambda r: r["real"]["precision_estancamiento"] >= 0.65),
    ("recall_estancamiento >= 0.65", lambda r: r["real"]["recall_estancamiento"] >= 0.65),
    ("ventaja_f1_sobre_heuristica >= 0.05", lambda r: r["real"]["f1_macro"] - r["heuristica"]["f1_macro"] >= 0.05),
    ("tramposo_f1 <= real_f1 - 0.10", lambda r: r["tramposo"]["f1_macro"] <= r["real"]["f1_macro"] - 0.10),
    ("permutadas_f1 <= 0.40", lambda r: r["permutadas"]["f1_macro"] <= 0.40),
    ("alumnos_detectados >= 0.90", lambda r: r["deteccion"]["pct_alumnos_detectados"] >= 0.90),
    ("retraso_mediano <= 4", lambda r: r["deteccion"]["retraso_mediano"] <= 4),
    ("falsas_alertas_progreso <= 0.15", lambda r: r["deteccion"]["pct_falsa_alerta_progreso"] <= 0.15),
]
UMBRALES_FOLD = UMBRALES[:3]   # los que se pueden mirar en una partición suelta


def resumen(valores):
    v = np.array(valores, dtype=float)
    return float(np.nanmean(v)), float(np.nanstd(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--semillas", type=int, default=10)
    ap.add_argument("--barrido-ruido", type=float, nargs="*", default=[])
    ap.add_argument("--out", default="reports/informe_metricas.json")
    a = ap.parse_args()
    cfg = cargar_config(a.config)
    semillas = [cfg["seed"] + i for i in range(a.semillas)]

    todo, folds, imps, cms = [], [], [], []
    for s in semillas:
        r, pf, imp, cm = evaluar_semilla(cfg, s)
        todo.append(r); folds.extend(pf); imps.append(imp); cms.append(cm)

    informe = {"semillas": semillas, "modelos": {}, "barrido_ruido": {}}

    # valores por semilla y % de semillas que cumple cada umbral
    claves = ("accuracy", "f1_macro", "precision_estancamiento", "recall_estancamiento")
    informe["por_semilla"] = [
        {"semilla": s, **{f"{n}_{k}": round(t[n][k], 4) for n in ("real", "heuristica", "tramposo", "permutadas") for k in claves},
         **{k: round(v, 4) for k, v in t["deteccion"].items()}}
        for s, t in zip(semillas, todo)]
    informe["cumplimiento_umbrales"] = {
        "sobre_la_media": None,  # se rellena abajo
        "pct_semillas": {n: float(np.mean([f(t) for t in todo])) for n, f in UMBRALES},
        "pct_folds_sueltos": {n: float(np.mean([f({"real": fo}) for fo in folds])) for n, f in UMBRALES_FOLD},
    }
    print(f"== {len(semillas)} semillas × 5 folds por alumno ==")
    print("Distribución de etiquetas:", {k: round(np.mean([t['distribucion'].get(k, 0) for t in todo]), 3) for k in CLASES})
    for nombre in ["real", "sin_ambiguos", "heuristica", "tramposo", "permutadas"]:
        informe["modelos"][nombre] = {}
        linea = []
        for k in todo[0][nombre]:
            m, sd = resumen([t[nombre][k] for t in todo])
            informe["modelos"][nombre][k] = {"media": m, "sd": sd}
            if k in ("accuracy", "f1_macro", "precision_estancamiento", "recall_estancamiento",
                     "precision_regresion", "recall_regresion"):
                linea.append(f"{k}={m:.2f}±{sd:.2f}")
        print(f"{nombre:13s}", "  ".join(linea))
    print("\nModelo real, dispersión ENTRE FOLDS (50 folds):")
    informe["por_fold"] = {}
    for k in ("accuracy", "f1_macro", "precision_estancamiento", "recall_estancamiento"):
        m, sd = resumen([f[k] for f in folds])
        informe["por_fold"][k] = {"media": m, "sd": sd}
        print(f"  {k}: {m:.2f} ± {sd:.2f}")
    media = {n: {k: v["media"] for k, v in d.items()} for n, d in informe["modelos"].items()}
    media["deteccion"] = {k: float(np.nanmean([t["deteccion"][k] for t in todo])) for k in todo[0]["deteccion"]}
    informe["cumplimiento_umbrales"]["sobre_la_media"] = {n: bool(f(media)) for n, f in UMBRALES}
    print("\nCumplimiento de umbrales (sobre la media | % semillas | % folds sueltos):")
    for n, _ in UMBRALES:
        c = informe["cumplimiento_umbrales"]
        pf = c["pct_folds_sueltos"].get(n)
        print(f"  {n:38s} {'sí' if c['sobre_la_media'][n] else 'NO':3s} | {c['pct_semillas'][n]*100:5.0f} % | "
              + (f"{pf*100:5.0f} %" if pf is not None else "    —"))
    m, _ = resumen([t["mayoritaria"] for t in todo])
    informe["clase_mayoritaria"] = m
    print(f"\nClase mayoritaria (sesiones 4-15): {m:.2f}")
    informe["deteccion"] = {}
    for k in todo[0]["deteccion"]:
        m, sd = resumen([t["deteccion"][k] for t in todo])
        informe["deteccion"][k] = {"media": m, "sd": sd}
        print(f"  {k}: {m:.2f} ± {sd:.2f}")
    for k in ("acierto_transicion_0_2", "acierto_asentado_3mas"):
        m, sd = resumen([t[k] for t in todo])
        informe[k] = {"media": m, "sd": sd}
        print(f"  {k}: {m:.2f} ± {sd:.2f}")
    imp = pd.Series(np.mean(imps, axis=0), index=columnas_features(cfg)).sort_values(ascending=False)
    informe["importancias"] = imp.round(4).to_dict()
    print("\nImportancia de variables (top 6):"); print(imp.head(6).round(3).to_string())
    cm = np.sum(cms, axis=0)
    informe["matriz_confusion"] = {"clases": CLASES, "filas_real_columnas_pred": cm.tolist()}
    print("\nMatriz de confusión acumulada (filas=real, columnas=predicho):")
    print(pd.DataFrame(cm, index=CLASES, columns=CLASES).to_string())

    if a.barrido_ruido:
        print("\n== Barrido de sigma_relativo (resto de config igual) ==")
        for sg in a.barrido_ruido:
            c = copy.deepcopy(cfg); c["ruido"]["sigma_relativo"] = sg
            rs = [evaluar_semilla(c, s, completo=False)[0]["real"] for s in semillas]
            fila = {k: dict(zip(("media", "sd"), resumen([r[k] for r in rs])))
                    for k in ("accuracy", "f1_macro", "precision_estancamiento", "recall_estancamiento")}
            informe["barrido_ruido"][str(sg)] = fila
            print(f"  sigma={sg:.2f}  " + "  ".join(f"{k}={v['media']:.2f}±{v['sd']:.2f}" for k, v in fila.items()))

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nInforme: {a.out}")


if __name__ == "__main__":
    main()
