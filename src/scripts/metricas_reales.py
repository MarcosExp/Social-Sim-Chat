#!/usr/bin/env python3
"""Calcula (o recalcula) las 5 métricas por sesión de las conversaciones reales terminadas y las compara
con el corpus sintético con el que se entrena el clasificador.

    python -m scripts.metricas_reales                 # añade las que falten (las registra la API al terminar)
    python -m scripts.metricas_reales --recalcular    # recalcula todas (p. ej. si cambia DEFINICION_VERSION)
    python -m scripts.metricas_reales --informe-solo  # solo la comparación

La comparación responde a una pregunta concreta: ¿las métricas que salen de conversaciones reales caen en el
mismo rango que vio el clasificador al entrenar? Si no, sus predicciones sobre sesiones reales no son fiables
aunque el recall sintético sea bueno. NO mide el recall real (no hay etiquetas de estancamiento reales).
"""
from __future__ import annotations

import argparse

import pandas as pd
from sqlalchemy import select, text

from app import metricas
from app.db import SessionLocal, engine
from app.models import Conversacion

COLS = ["aMLU", "latencia_pragmatica_ms", "IRC_pct", "PEPE", "pct_DET"]
# Nombre de la feature (pipeline) -> columna de la BD (ER v2, minúsculas)
COLS_DB = {"aMLU": "amlu", "latencia_pragmatica_ms": "latencia_pragmatica_ms", "IRC_pct": "irc_pct", "PEPE": "pepe", "pct_DET": "pct_det"}
SELECT_COLS = ", ".join(f'{db} AS "{py}"' for py, db in COLS_DB.items())


def etiqueta(col: str) -> str:
    if col in metricas.PROVISIONALES:
        return f"{col} (provisional)"
    return f"{col} (provisional: evaluador)" if col in metricas.PROVISIONALES_EVALUADOR else col


def notas_provisionales() -> list[str]:
    motivo = next(iter(metricas.PROVISIONALES_EVALUADOR.values()), None)
    notas = [f"(provisional) {k}: {m}. No es entrada del clasificador sobre sesiones reales."
             for k, m in metricas.PROVISIONALES.items()]
    if motivo:
        notas.append(f"(provisional: evaluador) {', '.join(metricas.PROVISIONALES_EVALUADOR)}: {motivo}; tratar sus cifras "
                     "como provisionales hasta arreglar el prompt de valoración.")
    return notas


def nota_granularidad(n_figuras: list[int]) -> str:
    """Aviso fijo: con pocas figuras por sesión PEPE y %DET solo toman unos pocos valores (decisión 7, 2026-10-12)."""
    n = [x for x in n_figuras if x]
    if not n:
        return "Sin figuras registradas todavía."
    lo, hi = min(n), max(n)
    saltos = sorted({round(100 / x) for x in n})
    rango_f = f"{lo}" if lo == hi else f"{lo}-{hi}"
    rango_s = f"{saltos[0]}" if len(saltos) == 1 else f"{saltos[0]}-{saltos[-1]}"
    return (f"Con {rango_f} figuras por sesión, PEPE y %DET dan saltos de {rango_s} puntos de la escala (100 / nº de figuras): "
            "comparar con un corpus continuo es sobre todo cualitativo.")


def sincronizar(recalcular: bool) -> tuple[int, int]:
    nuevas = actualizadas = 0
    with SessionLocal() as db:
        convs = db.scalars(select(Conversacion).where(Conversacion.estado == "terminada", Conversacion.es_prueba.is_(False))
                           .order_by(Conversacion.updated_at)).all()
        for conv in convs:
            previa = metricas.sesion_de(db, conv.conversacion_id)
            if previa is None:
                if metricas.registrar_sesion(db, conv):
                    nuevas += 1
            elif recalcular:
                metricas.recalcular_sesion(db, conv, previa)
                actualizadas += 1
    return nuevas, actualizadas


def fuera_de_rango(real: pd.Series, sint: pd.Series) -> tuple[float, float]:
    """% de valores reales fuera de [mín, máx] del corpus y fuera de [p5, p95] (más exigente: el corpus rara vez llega a los extremos)."""
    minmax = ((real < sint.min()) | (real > sint.max())).mean()
    p5p95 = ((real < sint.quantile(.05)) | (real > sint.quantile(.95))).mean()
    return round(float(100 * minmax), 1), round(float(100 * p5p95), 1)


def informe() -> dict:
    with engine.connect() as c:
        sint = pd.read_sql(text(f"SELECT {SELECT_COLS} FROM session_data WHERE origen = 'sintetico'"), c)
        real = pd.read_sql(text(f"SELECT {SELECT_COLS} FROM session_data WHERE origen = 'real'"), c)
        fig = pd.read_sql(text("SELECT n_figuras FROM session_data WHERE origen = 'real'"), c)
    out = {"n_sinteticas": len(sint), "n_reales": len(real), "metricas": {}, "provisionales": dict(metricas.PROVISIONALES),
           "n_figuras": [int(x) for x in fig["n_figuras"].dropna()]}
    for k in COLS:
        s, r = sint[k].astype(float), real[k].dropna().astype(float)
        fila = {"sintetico_p5_p50_p95": [round(float(s.quantile(q)), 2) for q in (.05, .5, .95)] if len(s) else None,
                "sintetico_min_max": [round(float(s.min()), 2), round(float(s.max()), 2)] if len(s) else None}
        fila["n_real"] = int(len(r))      # sesiones con valor (los nulos no cuentan)
        if len(r) and len(s):
            fuera_mm, fuera_p = fuera_de_rango(r, s)
            fila |= {"real_p50": round(float(r.median()), 2), "real_min_max": [round(float(r.min()), 2), round(float(r.max()), 2)],
                     "pct_fuera_del_rango_sintetico": fuera_mm, "pct_fuera_p5_p95": fuera_p}
        out["metricas"][k] = fila
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recalcular", action="store_true")
    ap.add_argument("--informe-solo", action="store_true")
    a = ap.parse_args()
    if not a.informe_solo:
        n, u = sincronizar(a.recalcular)
        print(f"Sesiones reales: {n} nuevas, {u} recalculadas (definición {metricas.DEFINICION_VERSION}).")
    r = informe()
    print(f"\nCorpus sintético: {r['n_sinteticas']} sesiones · reales: {r['n_reales']}\n")
    if not r["n_reales"]:
        print("Aún no hay sesiones reales terminadas: completa una conversación (make smoke) y repite.")
        return 0
    print(f"{'métrica':<34}{'sintético p5/p50/p95':<28}{'n':>5}{'real mediana':>13}{'real min-max':>20}{'fuera mín-máx':>15}{'fuera p5-p95':>14}")
    for k, v in r["metricas"].items():
        print(f"{etiqueta(k):<34}{str(v['sintetico_p5_p50_p95']):<28}{v.get('n_real', 0):>5}{v.get('real_p50', '-')!s:>13}"
              f"{str(v.get('real_min_max', '-')):>20}{str(v.get('pct_fuera_del_rango_sintetico', '-')) + ' %':>15}"
              f"{str(v.get('pct_fuera_p5_p95', '-')) + ' %':>14}")
    if r["n_figuras"]:
        f = sorted(r["n_figuras"])
        print(f"\nFiguras por sesión: mediana {f[len(f) // 2]}, mín-máx [{f[0]}, {f[-1]}] · {nota_granularidad(f)}")
    for nota in notas_provisionales():
        print(f"\n{nota}")
    if r["n_reales"] < 20:
        print(f"\nAviso: con {r['n_reales']} sesiones reales la comparación es orientativa (conviene ≥ 20).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
