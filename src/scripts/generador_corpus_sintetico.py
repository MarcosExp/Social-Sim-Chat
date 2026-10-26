#!/usr/bin/env python3
"""
generador_corpus_sintetico.py — SOCIAL-SIM Chat

Genera el corpus sintético de sesiones (`student_profile_sim` + `session_data`)
a partir de las especificaciones ya cerradas en:
  - Perfiles_Alumno_Simulado.md  (4 arquetipos: A progreso, B estancamiento,
    C regresión, D progreso ruidoso; rangos de las 5 métricas por fase/sesión)
  - Guiones_Dialogo.md           (nº de turnos evaluables por competencia:
    Metáfora=4, Sarcasmo=3, Preguntas recíprocas=3, Deixis=3, + apertura Guion 0)

Esqueleto de partida para Marcos (plataforma/ingeniería ML) — punto de partida,
no implementación final: la parte de especificación pedagógica/de datos (Álvaro)
está cerrada; lo que sigue abierto y depende de decisiones de plataforma es:
  - si esto se ejecuta como script batch (como está aquí) o como parte del
    pipeline de features del backend;
  - el formato final de persistencia (aquí se vuelca a CSV; para Postgres
    bastaría con un INSERT por fila o `to_sql` con SQLAlchemy);
  - si el campo `turnos` se queda como JSON embebido en `session_data` (como
    en el ER de NF2) o se normaliza en una tabla `turn_data` aparte.

Volumen por defecto: 25 alumnos simulados por arquetipo (100 en total) x el
nº de sesiones ya fijado por perfil (14-16) x 6-7 turnos/sesión — coherente
con la estimación cerrada en la sección 8 del NF2 (~1.500 sesiones,
~10.000 eventos de turno).

Uso:
    python3 generador_corpus_sintetico.py --seed 42 --n-por-arquetipo 25 \
        --out-dir ./corpus_sintetico

Salida:
    <out-dir>/student_profile_sim.csv
    <out-dir>/session_data.csv   (con columna `turnos` como JSON serializado)
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Especificación de los 4 arquetipos (fuente: Perfiles_Alumno_Simulado.md)
# ---------------------------------------------------------------------------

METRICAS = ["aMLU", "latencia_pragmatica_ms", "IRC_pct", "PEPE", "pct_DET"]

# Rango global (mín, máx) de cada métrica en TODO el corpus, usado solo para
# normalizar la probabilidad de acierto por turno (0/1/2), no como límite duro.
RANGO_GLOBAL = {
    "aMLU": (2.3, 4.8),
    "latencia_pragmatica_ms": (2200, 5800),
    "IRC_pct": (10, 60),
    "PEPE": (0.2, 1.6),
    "pct_DET": (15, 85),
}


def _interp(a: float, b: float, frac: float) -> float:
    """Interpolación lineal simple entre a y b, frac en [0, 1]."""
    return a + (b - a) * frac


def _con_ruido(valor: float, ruido_rel: float, rng: np.random.Generator) -> float:
    """Añade ruido gaussiano proporcional (± ruido_rel) a un valor central."""
    return float(valor * (1 + rng.normal(0, ruido_rel)))


@dataclass
class Arquetipo:
    codigo: str  # A, B, C, D
    competencia: str
    tramo_edad: str
    n_sesiones: int
    # función que, dado el nº de sesión (1-indexed) y un rng, devuelve un dict
    # con las 5 métricas para ESA sesión (antes de aplicar el offset por alumno)
    curva: Callable[[int, np.random.Generator], dict[str, float]]


def _curva_A(sesion: int, rng: np.random.Generator) -> dict:
    # Progreso sostenido, 3 fases: 1-3 / 4-8 / 9-15
    fases = {
        (1, 3): dict(aMLU=(2.5, 3.0), latencia_pragmatica_ms=(5500, 4500),
                     IRC_pct=(15, 25), PEPE=(0.3, 0.5), pct_DET=(20, 30)),
        (4, 8): dict(aMLU=(3.2, 3.8), latencia_pragmatica_ms=(4200, 3500),
                     IRC_pct=(30, 40), PEPE=(0.7, 1.0), pct_DET=(40, 55)),
        (9, 15): dict(aMLU=(4.0, 4.6), latencia_pragmatica_ms=(3200, 2500),
                      IRC_pct=(45, 55), PEPE=(1.2, 1.5), pct_DET=(65, 80)),
    }
    for (ini, fin), rangos in fases.items():
        if ini <= sesion <= fin:
            frac = (sesion - ini) / max(1, fin - ini)
            return {m: _interp(lo, hi, frac) for m, (lo, hi) in rangos.items()}
    raise ValueError(f"sesión {sesion} fuera de rango para arquetipo A")


def _curva_B(sesion: int, rng: np.random.Generator) -> dict:
    # Progreso 1-7, meseta (estancamiento) 8-16
    if sesion <= 7:
        frac = (sesion - 1) / 6
        return dict(
            aMLU=_interp(2.8, 3.6, frac),
            latencia_pragmatica_ms=_interp(5000, 3800, frac),
            IRC_pct=_interp(20, 38, frac),
            PEPE=_interp(0.4, 0.9, frac),
            pct_DET=_interp(25, 50, frac),
        )
    # meseta: rango plano con pequeño ruido, sin tendencia neta
    return dict(
        aMLU=rng.uniform(3.5, 3.7),
        latencia_pragmatica_ms=rng.uniform(3700, 3900),
        IRC_pct=rng.uniform(36, 40),
        PEPE=rng.uniform(0.85, 0.95),
        pct_DET=rng.uniform(48, 52),
    )


def _curva_C(sesion: int, rng: np.random.Generator) -> dict:
    # Progreso 1-9, regresión 10-14
    if sesion <= 9:
        frac = (sesion - 1) / 8
        return dict(
            aMLU=_interp(3.0, 4.2, frac),
            latencia_pragmatica_ms=_interp(4800, 3000, frac),
            IRC_pct=_interp(22, 48, frac),
            PEPE=_interp(0.4, 1.3, frac),
            pct_DET=_interp(22, 70, frac),
        )
    frac = (sesion - 10) / 4
    return dict(
        aMLU=_interp(3.9, 3.3, frac),
        latencia_pragmatica_ms=_interp(3400, 4300, frac),
        IRC_pct=_interp(44, 28, frac),
        PEPE=_interp(1.1, 0.6, frac),
        pct_DET=_interp(62, 35, frac),
    )


def _curva_D(sesion: int, rng: np.random.Generator) -> dict:
    # Progreso con alta variabilidad ("dientes de sierra"), 15 sesiones
    frac = (sesion - 1) / 14
    base = dict(
        aMLU=_interp(2.6, 3.9, frac),
        latencia_pragmatica_ms=_interp(5200, 3400, frac),
        IRC_pct=_interp(18, 42, frac),
        PEPE=_interp(0.3, 1.1, frac),
        pct_DET=_interp(20, 60, frac),
    )
    # ruido alto + "sesiones malas" ocasionales (peor de lo esperado)
    sesion_mala = rng.random() < 0.20
    ruido = {
        "aMLU": 0.10, "latencia_pragmatica_ms": 0.08,
        "IRC_pct": 0.15, "PEPE": 0.18, "pct_DET": 0.15,
    }
    out = {}
    for m, v in base.items():
        v2 = _con_ruido(v, ruido[m], rng)
        if sesion_mala:
            # empeora la métrica (más latencia, menos del resto)
            v2 = v2 * 1.18 if m == "latencia_pragmatica_ms" else v2 * 0.75
        out[m] = v2
    return out


ARQUETIPOS = {
    "A": Arquetipo("A", "Metáfora", "6-8", 15, _curva_A),
    "B": Arquetipo("B", "Sarcasmo", "8-10", 16, _curva_B),
    "C": Arquetipo("C", "Preguntas recíprocas", "10-12", 14, _curva_C),
    "D": Arquetipo("D", "Deixis", "6-8", 15, _curva_D),
}

# Nº de turnos evaluables por guion de competencia (fuente: Guiones_Dialogo.md)
TURNOS_POR_COMPETENCIA = {
    "Metáfora": 4,
    "Sarcasmo": 3,
    "Preguntas recíprocas": 3,
    "Deixis": 3,
}
TURNOS_APERTURA = 2  # Guion 0, no evaluado (no genera accuracy_score)

ETIQUETA_POR_ARQUETIPO_Y_FASE = {
    # (codigo, sesion) -> etiqueta real diseñada, coherente con
    # Perfiles_Alumno_Simulado.md
    "A": lambda s: "Progreso",
    "B": lambda s: "Progreso" if s <= 7 else "Estancamiento",
    "C": lambda s: "Progreso" if s <= 9 else "Regresión",
    "D": lambda s: "Progreso",  # progreso ruidoso sigue siendo progreso real
}


# ---------------------------------------------------------------------------
# 2. Generación de alumnos y sesiones
# ---------------------------------------------------------------------------

def generar_turnos(competencia: str, pepe: float, pct_det: float,
                    latencia_media: float, rng: np.random.Generator) -> list[dict]:
    """Genera los eventos de turno de una sesión: primero los de apertura
    (Guion 0 — no evaluados, solo registran si hubo respuesta y la rama
    seguida), luego los de la competencia con accuracy_score 0/1/2, coherente
    con dónde cae PEPE dentro del rango global (progreso implica mayor
    probabilidad de acierto)."""
    turnos: list[dict] = []

    # --- Guion 0 (apertura, no evaluado) ---
    for t in range(1, TURNOS_APERTURA + 1):
        turnos.append({
            "turno": t,
            "tipo": "apertura",
            "hubo_respuesta": bool(rng.random() < 0.9),
            "rama": rng.choice(["2.A", "2.B"]) if t == 2 else None,
            "latencia_ms": round(max(400, rng.normal(latencia_media * 0.8, latencia_media * 0.2))),
        })

    # --- turnos de la competencia (evaluados) ---
    n_turnos = TURNOS_POR_COMPETENCIA[competencia]
    lo, hi = RANGO_GLOBAL["PEPE"]
    progreso_frac = np.clip((pepe - lo) / (hi - lo), 0, 1)
    # p2 (correcto) crece con el progreso; p0 (literal) decrece
    p2 = 0.15 + 0.65 * progreso_frac
    p0 = 0.55 - 0.45 * progreso_frac
    p1 = max(0.05, 1 - p2 - p0)
    probs = np.array([p0, p1, p2])
    probs = probs / probs.sum()

    for t in range(1, n_turnos + 1):
        accuracy_score = int(rng.choice([0, 1, 2], p=probs))
        latencia_turno = max(400, rng.normal(latencia_media, latencia_media * 0.18))
        turnos.append({
            "turno": TURNOS_APERTURA + t,
            "tipo": "competencia",
            "accuracy_score": accuracy_score,
            "latencia_ms": round(latencia_turno),
        })
    return turnos


def generar_corpus(n_por_arquetipo: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng_maestro = np.random.default_rng(seed)
    perfiles_rows = []
    sesiones_rows = []

    for codigo, arq in ARQUETIPOS.items():
        for i in range(1, n_por_arquetipo + 1):
            student_id = f"sim-{codigo}-{i:03d}"
            rng = np.random.default_rng(rng_maestro.integers(0, 2**32 - 1))

            # offset propio de este alumno simulado (variabilidad entre
            # instancias del mismo arquetipo, no solo dentro de una sesión)
            offset_escala = {m: rng.normal(1.0, 0.04) for m in METRICAS}

            perfiles_rows.append({
                "student_id": student_id,
                "competencia_objetivo": arq.competencia,
                "trayectoria_disenada": {
                    "A": "Progreso", "B": "Estancamiento",
                    "C": "Regresión", "D": "Progreso (alta variabilidad)",
                }[codigo],
                "tramo_edad": arq.tramo_edad,
                "n_sesiones": arq.n_sesiones,
            })

            for s in range(1, arq.n_sesiones + 1):
                metricas = arq.curva(s, rng)
                metricas = {m: v * offset_escala[m] for m, v in metricas.items()}

                turnos = generar_turnos(
                    arq.competencia, metricas["PEPE"], metricas["pct_DET"],
                    metricas["latencia_pragmatica_ms"], rng,
                )
                turnos_competencia = [t for t in turnos if t["tipo"] == "competencia"]
                pct_det_real = 100 * sum(
                    1 for t in turnos_competencia if t["accuracy_score"] == 2
                ) / len(turnos_competencia)

                sesiones_rows.append({
                    "session_id": str(uuid.uuid4()),
                    "student_id": student_id,
                    "sesion_num": s,
                    "competencia": arq.competencia,
                    "aMLU": round(metricas["aMLU"], 2),
                    "latencia_pragmatica_ms": round(metricas["latencia_pragmatica_ms"]),
                    "IRC_pct": round(metricas["IRC_pct"], 1),
                    "PEPE": round(metricas["PEPE"], 2),
                    "pct_DET": round(metricas["pct_DET"], 1),
                    "pct_DET_observado_en_turnos": round(pct_det_real, 1),
                    "etiqueta_real_disenada": ETIQUETA_POR_ARQUETIPO_Y_FASE[codigo](s),
                    "turnos": json.dumps(turnos, ensure_ascii=False),
                })

    df_perfiles = pd.DataFrame(perfiles_rows)
    df_sesiones = pd.DataFrame(sesiones_rows)
    return df_perfiles, df_sesiones


# ---------------------------------------------------------------------------
# 3. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-por-arquetipo", type=int, default=25,
                         help="Alumnos simulados a generar por cada uno de los "
                              "4 arquetipos (por defecto 25 → 100 en total, "
                              "coherente con la sección 8 del NF2).")
    parser.add_argument("--out-dir", type=str, default="./corpus_sintetico")
    args = parser.parse_args()

    df_perfiles, df_sesiones = generar_corpus(args.n_por_arquetipo, args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df_perfiles.to_csv(out_dir / "student_profile_sim.csv", index=False)
    df_sesiones.to_csv(out_dir / "session_data.csv", index=False)

    n_turnos_total = sum(len(json.loads(t)) for t in df_sesiones["turnos"])
    print(f"Alumnos simulados generados : {len(df_perfiles)}")
    print(f"Sesiones generadas          : {len(df_sesiones)}")
    print(f"Eventos de turno generados  : {n_turnos_total}")
    print(f"Escrito en                  : {out_dir.resolve()}")
    print()
    print("Resumen de etiqueta real diseñada por sesión:")
    print(df_sesiones["etiqueta_real_disenada"].value_counts().to_string())


if __name__ == "__main__":
    main()
