#!/usr/bin/env python3
"""Genera el corpus sintético (reutilizando generador_corpus_sintetico.py
tal cual, heredado del TFM) y lo carga en Postgres.

Uso (dentro del contenedor backend o con DATABASE_URL apuntando a localhost):

    python -m scripts.seed_corpus --reset                 # corpus corregido de Marcos (por defecto)
    python -m scripts.seed_corpus --generador heredado    # generador anterior (filtra la etiqueta)
    python -m scripts.seed_corpus --reset --sin-turnos    # sin las conversaciones y turnos sintéticos (generar_turnos.py)

También puedes ejecutarlo contra el contenedor en marcha:

    docker compose -f environment/docker-compose.yml exec backend \
        python -m scripts.seed_corpus
"""
from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal

SRC = Path(__file__).resolve().parent.parent
ETIQUETA = {"progreso": "progreso", "estancamiento": "estancamiento", "regresion": "regresion"}   # ER v2: minúsculas, sin tilde


def etiqueta_db(e: str) -> str:
    """Normaliza etiquetas de cualquier generador («Progreso», «Regresión», «Progreso (alta variabilidad)») al valor de la BD."""
    return e.split(" (")[0].strip().lower().replace("ó", "o")
NIVELES_RUIDO = {"bajo", "medio", "alto"}   # ER v2: student_profile_sim.nivel_ruido
NS = uuid.UUID("5d85eb0c-0000-4000-8000-50c1a15101c0")  # UUIDs deterministas: misma semilla -> mismos ids


def corpus_marcos(seed: int | None):
    """Adapta el corpus corregido de Marcos (src/generador/, sin modificar) al esquema de la BD."""
    from generador.generador_corpus_sintetico import cargar_config, generar_corpus

    cfg = cargar_config(SRC / "generador" / "config.yaml")
    train, meta = generar_corpus(cfg, seed)
    n_ses = train.groupby("alumno_id").size()
    columnas = ["student_id", "competencia_objetivo", "trayectoria_disenada", "tramo_edad", "n_sesiones",
                "sesion_inicio_evento", "arquetipo", "ambiguo", "tipo_ambiguo"]
    if "nivel_ruido" in meta:   # lo añade el generador de Marcos (acuerdo del 25/10/2026); con el anterior queda en NULL
        invalidos = sorted(set(meta["nivel_ruido"].dropna()) - NIVELES_RUIDO)
        if invalidos:
            raise ValueError(f"nivel_ruido solo admite {sorted(NIVELES_RUIDO)} (ER v2); el generador devolvió {invalidos}")
        columnas.append("nivel_ruido")
    perfiles = meta.assign(
        student_id=meta["alumno_id"],
        competencia_objetivo=meta["competencia"],
        trayectoria_disenada=meta["trayectoria"].map(ETIQUETA),
        tramo_edad=None,
        n_sesiones=meta["alumno_id"].map(n_ses),
        ambiguo=meta["ambiguo"].astype(bool),
        tipo_ambiguo=meta["tipo_ambiguo"].replace("", None),
        sesion_inicio_evento=meta["inicio_cambio"],      # nombre del ER (migración 008)
    )[columnas]
    comp = meta.set_index("alumno_id")["competencia"]
    sesiones = train.assign(
        session_id=[str(uuid.uuid5(NS, f"{a}-{n}")) for a, n in zip(train["alumno_id"], train["sesion"])],
        student_id=train["alumno_id"],
        sesion_num=train["sesion"],
        competencia=train["alumno_id"].map(comp),
        latencia_pragmatica_ms=train["latencia_pragmatica_ms"],
        pct_DET_observado_en_turnos=None,   # este generador no produce turnos
        etiqueta_real_disenada=train["etiqueta"].map(ETIQUETA),
    )[["session_id", "student_id", "sesion_num", "competencia", "aMLU", "latencia_pragmatica_ms", "IRC_pct",
       "PEPE", "pct_DET", "pct_DET_observado_en_turnos", "etiqueta_real_disenada"]]
    return perfiles, sesiones


def corpus_heredado(n_por_arquetipo: int, seed: int):
    from scripts.generador_corpus_sintetico import generar_corpus

    return generar_corpus(n_por_arquetipo, seed)


def seed(generador: str, n_por_arquetipo: int, seed: int | None, reset: bool, turnos: bool = True) -> None:
    if generador == "marcos":
        df_perfiles, df_sesiones = corpus_marcos(seed)
    else:
        df_perfiles, df_sesiones = corpus_heredado(n_por_arquetipo, 42 if seed is None else seed)
    df_perfiles = df_perfiles.astype(object).where(df_perfiles.notna(), None)
    df_sesiones = df_sesiones.astype(object).where(df_sesiones.notna(), None)
    if "turnos" in df_sesiones:   # el generador heredado los trae; el ER v2 no los guarda en session_data (migración 012)
        print("Aviso: se descartan los turnos del generador heredado (session_data ya no tiene columna `turnos`).")
        df_sesiones = df_sesiones.drop(columns=["turnos"])
    for col in ("sesion_inicio_evento", "n_sesiones"):
        if col in df_perfiles:
            df_perfiles[col] = [None if v is None else int(v) for v in df_perfiles[col]]

    db = SessionLocal()
    try:
        if reset:  # todo el contenido es sintético: se puede vaciar sin riesgo
            db.execute(text("TRUNCATE student_profile_sim CASCADE"))
        for _, row in df_perfiles.iterrows():
            db.execute(
                text(
                    """
                    INSERT INTO student_profile_sim
                        (student_id, competencia_objetivo, trayectoria_disenada, tramo_edad, n_sesiones,
                         sesion_inicio_evento, arquetipo, nivel_ruido, ambiguo, tipo_ambiguo)
                    VALUES (:student_id, :competencia_objetivo, :trayectoria_disenada, :tramo_edad, :n_sesiones,
                            :sesion_inicio_evento, :arquetipo, :nivel_ruido, :ambiguo, :tipo_ambiguo)
                    ON CONFLICT (student_id) DO NOTHING
                    """
                ),
                {"sesion_inicio_evento": None, "arquetipo": None, "nivel_ruido": None, "ambiguo": None, "tipo_ambiguo": None,
                 **row.to_dict(), "trayectoria_disenada": etiqueta_db(row["trayectoria_disenada"])},
            )

        for _, row in df_sesiones.iterrows():
            data = row.to_dict()
            data["etiqueta_real_disenada"] = etiqueta_db(data["etiqueta_real_disenada"])
            db.execute(
                text(
                    """
                    INSERT INTO session_data
                        (session_id, student_id, sesion_num, competencia, origen, amlu,
                         latencia_pragmatica_ms, irc_pct, pepe, pct_det,
                         pct_det_observado_en_turnos, etiqueta_real_disenada)
                    VALUES
                        (:session_id, :student_id, :sesion_num, :competencia, 'sintetico', :aMLU,
                         :latencia_pragmatica_ms, :IRC_pct, :PEPE, :pct_DET,
                         :pct_DET_observado_en_turnos, :etiqueta_real_disenada)
                    ON CONFLICT (student_id, sesion_num) DO NOTHING
                    """
                ),
                data,
            )

        resumen_turnos = None
        if turnos and generador == "marcos":   # conversaciones + turnos de cada sesión (migración 013), en la misma transacción
            from scripts import generar_turnos
            resumen_turnos = generar_turnos.sembrar(db, seed)
        db.commit()
    finally:
        db.close()

    print(f"Cargados {len(df_perfiles)} alumnos simulados y {len(df_sesiones)} sesiones en la base de datos.")
    if resumen_turnos:
        n_conv, n_turnos, n_enlazadas = resumen_turnos
        print(f"Turnos sintéticos: {n_conv} conversaciones, {n_turnos} filas de turno, {n_enlazadas} sesiones enlazadas.")
    elif turnos and generador != "marcos":
        print("Aviso: generar_turnos.py solo trabaja con el generador de Marcos; el heredado se carga sin turnos.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generador", choices=["marcos", "heredado"], default="marcos")
    parser.add_argument("--seed", type=int, default=None, help="por defecto, la de config.yaml (marcos) o 42 (heredado)")
    parser.add_argument("--n-por-arquetipo", type=int, default=25, help="solo generador heredado")
    parser.add_argument("--reset", action="store_true", help="vacía las tablas antes de cargar")
    parser.add_argument("--sin-turnos", action="store_true",
                        help="no crea las conversaciones y turnos sintéticos de cada sesión (generar_turnos.py)")
    args = parser.parse_args()
    print(f"Generador: {args.generador}")
    seed(args.generador, args.n_por_arquetipo, args.seed, args.reset, turnos=not args.sin_turnos)


if __name__ == "__main__":
    main()
