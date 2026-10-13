#!/usr/bin/env python3
"""
generador_corpus_sintetico.py — SOCIAL-SIM Chat

Genera el corpus sintético de sesiones siguiendo `cambios-generador-corpus.md`
(secciones 1, 2, 3 y 5). Todos los parámetros se leen de `config.yaml`.

Salida (dos ficheros, para que los metadatos no puedan usarse por error):
    corpus_train.csv  alumno_id, sesion, 5 métricas, etiqueta
    corpus_meta.csv   alumno_id, competencia, arquetipo, trayectoria,
                      inicio_cambio, ambiguo, tipo_ambiguo

Uso:
    python src/generador/generador_corpus_sintetico.py --config config.yaml \
        --out-dir data/corpus_sintetico

Corpus sintético: las métricas de un modelo entrenado con él miden si aprende
los patrones programados por el equipo, no eficacia clínica. Los casos
ambiguos y el ruido están puestos a propósito.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

COMPETENCIAS = ["Metáfora", "Sarcasmo", "Preguntas recíprocas", "Deixis"]
ARQUETIPO = {"Metáfora": "A", "Sarcasmo": "B", "Preguntas recíprocas": "C", "Deixis": "D"}
ETIQUETAS = ["estancamiento", "progreso", "regresion"]


def cargar_config(ruta: str | Path) -> dict:
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f)


def aplicar_ambiguedad(inicio: int, escala: float, rng: np.random.Generator,
                       cfg: dict) -> tuple[int, float, str]:
    """Devuelve (inicio, escala, tipo) para un alumno ambiguo."""
    tipo = str(rng.choice(cfg["ambiguos"]["tipos"]))
    if tipo == "inicio_tardio":
        inicio = int(rng.choice([11, 12]))
    elif tipo == "pendiente_debil":
        escala *= 0.3
    # cambio_de_signo se resuelve sesión a sesión en generar_alumno
    return inicio, escala, tipo


def _otra_etiqueta(etiqueta: str, rng: np.random.Generator) -> str:
    return str(rng.choice([e for e in ETIQUETAS if e != etiqueta]))


def generar_alumno(i: int, cfg: dict, rng: np.random.Generator) -> tuple[list[dict], dict]:
    met = cfg["metricas"]
    nombres = list(met)
    pend_base = np.array([met[m]["pendiente"] for m in nombres], dtype=float)
    rango = np.array([met[m]["rango"] for m in nombres], dtype=float)
    lo = np.array([met[m]["min"] for m in nombres], dtype=float)
    hi = np.array([met[m]["max"] for m in nombres], dtype=float)
    signo = np.sign(pend_base)          # dirección de "mejorar" en cada métrica

    alumno_id = f"sim-{i + 1:03d}"
    competencia = COMPETENCIAS[i % 4]
    p = [cfg["emparejamiento"][competencia][e] for e in ETIQUETAS]
    trayectoria = str(rng.choice(ETIQUETAS, p=p))
    inicio = int(rng.integers(cfg["inicio_cambio"]["min"], cfg["inicio_cambio"]["max"] + 1))
    escala = float(rng.uniform(*cfg["pendiente"]["variacion_por_alumno"]))
    ambiguo = bool(rng.random() < cfg["ambiguos"]["proporcion"])
    tipo_ambiguo = ""
    if ambiguo:
        inicio, escala, tipo_ambiguo = aplicar_ambiguedad(inicio, escala, rng, cfg)

    n = cfg["n_sesiones"]
    # cambio_de_signo: la tendencia se invierte a mitad del tramo que sigue al
    # inicio del cambio (o a mitad de la trayectoria si el alumno progresa).
    if trayectoria == "progreso":
        s_inversion = n // 2 + 1
    else:
        s_inversion = inicio + max(1, (n - inicio + 1) // 2)

    # nivel inicial propio del alumno
    nivel = np.array([met[m]["inicio"] for m in nombres], dtype=float)
    nivel += rng.normal(0, cfg["baseline_sigma_relativo"], len(nombres)) * rango

    factor_ruido = cfg["altibajos"]["oscilacion_perfil_D"] if competencia == "Deixis" else 1.0
    sigma = cfg["ruido"]["sigma_relativo"] * rango * factor_ruido
    sigma_med = cfg["ruido"]["ruido_medicion"] * rango
    rho = cfg["ruido"]["ar1_rho"]
    alt = cfg["altibajos"]

    ar = np.zeros(len(nombres))
    recaida_restante, recaida_mag = 0, 0.0
    filas = []
    for s in range(1, n + 1):
        en_cambio = s >= inicio and trayectoria != "progreso"
        mult = cfg["pendiente"][trayectoria] if en_cambio else cfg["pendiente"]["progreso"]
        if tipo_ambiguo == "cambio_de_signo" and s >= s_inversion:
            # progreso -> cae; estancamiento -> vuelve a progresar; regresión -> remonta
            mult = {"progreso": cfg["pendiente"]["regresion"],
                    "estancamiento": cfg["pendiente"]["progreso"],
                    "regresion": -cfg["pendiente"]["regresion"]}[trayectoria]
        nivel = nivel + mult * escala * pend_base

        # ruido AR(1) (varianza estacionaria = sigma²) + ruido de medición
        ar = rho * ar + np.sqrt(1 - rho ** 2) * rng.normal(0, 1, len(nombres)) * sigma
        medicion = rng.normal(0, 1, len(nombres)) * sigma_med

        # recaída puntual: empeora todas las métricas durante 1-2 sesiones
        if recaida_restante == 0 and rng.random() < alt["p_recaida_por_sesion"]:
            recaida_restante = int(rng.integers(alt["duracion_sesiones"][0],
                                                alt["duracion_sesiones"][1] + 1))
            recaida_mag = float(rng.uniform(*alt["magnitud_sigma"]))
        recaida = np.zeros(len(nombres))
        if recaida_restante > 0:
            recaida = -signo * recaida_mag * sigma
            recaida_restante -= 1

        valores = np.clip(nivel + ar + medicion + recaida, lo, hi)

        # etiqueta por diseño: no se recalcula a partir de la trayectoria ruidosa
        etiqueta = trayectoria if en_cambio else "progreso"
        if rng.random() < cfg["ruido_etiqueta"]:
            etiqueta = _otra_etiqueta(etiqueta, rng)

        fila = {"alumno_id": alumno_id, "sesion": s}
        fila.update({
            "aMLU": round(float(valores[0]), 2),
            "latencia_pragmatica_ms": int(round(float(valores[1]))),
            "IRC_pct": round(float(valores[2]), 1),
            "PEPE": round(float(valores[3]), 2),
            "pct_DET": round(float(valores[4]), 1),
        })
        fila["etiqueta"] = etiqueta
        filas.append(fila)

    meta = {
        "alumno_id": alumno_id,
        "competencia": competencia,
        "arquetipo": ARQUETIPO[competencia],
        "trayectoria": trayectoria,
        "inicio_cambio": inicio,
        "ambiguo": ambiguo,
        "tipo_ambiguo": tipo_ambiguo,
    }
    return filas, meta


def generar_corpus(cfg: dict, seed: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (corpus_train, corpus_meta). Misma semilla → mismo corpus."""
    assert list(cfg["metricas"]) == ["aMLU", "latencia_pragmatica_ms", "IRC_pct", "PEPE", "pct_DET"]
    maestro = np.random.SeedSequence(cfg["seed"] if seed is None else seed)
    filas, metas = [], []
    for i, ss in enumerate(maestro.spawn(cfg["n_alumnos"])):
        f, m = generar_alumno(i, cfg, np.random.default_rng(ss))
        filas.extend(f)
        metas.append(m)
    return pd.DataFrame(filas), pd.DataFrame(metas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generador de corpus sintético SOCIAL-SIM Chat")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--seed", type=int, default=None, help="sustituye a la semilla de config.yaml")
    parser.add_argument("--out-dir", default="data/corpus_sintetico")
    args = parser.parse_args()

    cfg = cargar_config(args.config)
    train, meta = generar_corpus(cfg, args.seed)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    train.to_csv(out / "corpus_train.csv", index=False)
    meta.to_csv(out / "corpus_meta.csv", index=False)

    print(f"Alumnos: {len(meta)}   Sesiones: {len(train)}   Escrito en: {out.resolve()}")
    print("\nEtiquetas por sesión (%):")
    print((train["etiqueta"].value_counts(normalize=True) * 100).round(1).to_string())
    print("\nTrayectoria por competencia (alumnos):")
    print(pd.crosstab(meta["competencia"], meta["trayectoria"]).to_string())
    print(f"\nAmbiguos: {int(meta['ambiguo'].sum())}")


if __name__ == "__main__":
    main()
