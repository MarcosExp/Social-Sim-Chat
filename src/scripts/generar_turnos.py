"""Turnos sintéticos coherentes con las métricas de cada sesión del corpus (contrato: ADR-001, addendum 013).

Qué hace (NF2, secciones 7 y 8): para cada sesión sintética del generador de Marcos crea una conversación terminada
y sus turnos, con la misma forma que guarda el chat real (`conversacion` + `conversacion_turno`, una fila por intento).
Los turnos alimentan la base de datos y el dashboard (vista `turn_data`), NUNCA el clasificador: el clasificador se
entrena con las métricas de sesión que ya genera el generador.

Cómo se derivan los turnos de las métricas de la sesión (definición de métricas reales v3, `app/metricas.py`):
- PEPE y %DET -> puntuación 0/1/2 de cada figura. Se elige la combinación de figuras con Σ puntos = round(PEPE · n)
  cuyo % de intentos valorados con 2 queda más cerca del %DET de la sesión. Regla de intentos: 2 = acierta a la primera
  (un intento); 1 = falla o es parcial y acierta tras la ayuda (dos intentos); 0 = no acierta en ninguno de los dos.
- LPP -> latencias de todos los turnos del menor, desplazadas para que su mediana sea exactamente la LPP de la sesión.
- aMLU -> nº de palabras de los turnos de competencia valorados >= 1, repartidas para que su media sea la aMLU.
- IRC % -> se marca como pregunta («?», no cambia el nº de palabras) el nº de turnos necesario para llegar al IRC.

Límites conocidos (para la memoria): con 3-4 figuras por sesión PEPE solo puede tomar valores discretos, así que la PEPE
recalculada desde los turnos se aparta de la de la sesión hasta 1/(2n); en «Preguntas recíprocas» cada turno valorado
con 2 cuenta como iniciativa, así que el IRC recalculado no puede bajar de ese mínimo; el %DET del diseño (RQA entre
sesiones) no se reproduce, solo el % de intentos con 2 (`pct_DET_observado_en_turnos`). El texto de los turnos es de
relleno: sirve para contar palabras, no para leerlo como una respuesta real.

En la base de datos (migración 013): cada conversación va con `origen='sintetico'` y `es_prueba=true` (así las métricas
reales, los listados y el dashboard no la ven), los turnos del menor con `evaluacion_origen='sintetico'`, y cada sesión
sintética se enlaza con su conversación por `session_id` (el mismo uuid5 que `seed_corpus`). `session_data` no se recalcula
desde los turnos. Lo hace `seed_corpus.py` al final de la carga (`--sin-turnos` para saltarlo), llamando a `sembrar`.

Uso sin base de datos (escribe CSV y una comprobación turno -> métricas):
    python -m scripts.generar_turnos --out-dir data/turnos_sinteticos
"""
from __future__ import annotations

import argparse
import math
import uuid
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app import metricas
from app.guiones import Guion, Guiones, cargar_guiones

SRC = Path(__file__).resolve().parent.parent
NS = uuid.UUID("5d85eb0c-0000-4000-8000-50c1a15101c0")      # el mismo espacio que seed_corpus: mismos session_id
VERSION = "generar_turnos-0.1"
ORIGEN_EVALUACION = "sintetico"   # admitido por el CHECK de conversacion_turno.evaluacion_origen desde la migración 013
P_PARCIAL = 0.4                   # prob. de que un intento fallido sea «parcial» (1) en vez de 0
RELLENO = ["pues", "creo", "que", "es", "eso", "a", "lo", "mejor", "porque", "sí"]
FALLOS = ["no sé", "vale", "explota", "que se cae", "nada"]
APERTURA_MENOR = [("a1", "responde", "bien"), ("a2", "afirmativa", "vale")]


# --------------------------------------------------------------------------- piezas puras
def composicion_figuras(pepe: float, pct_det: float, n: int) -> tuple[int, int, int]:
    """(n2, n1, n0) con 2·n2 + n1 = round(PEPE·n) y % de intentos con 2 lo más cerca posible del %DET."""
    total = int(np.clip(round(pepe * n), 0, 2 * n))
    candidatas = [(n2, total - 2 * n2, n - n2 - (total - 2 * n2))
                  for n2 in range(total // 2 + 1) if 0 <= total - 2 * n2 <= n - n2]

    def pct_dos(c):
        n2, n1, n0 = c
        return 100 * (n2 + n1) / (n2 + 2 * (n1 + n0))
    return min(candidatas, key=lambda c: (abs(pct_dos(c) - pct_det), c))


def intentos_de_figura(score: int, rng: np.random.Generator) -> list[int]:
    """Valoraciones por intento que producen esa puntuación de figura (regla de `metricas.puntuar_figuras`)."""
    fallo = lambda: 1 if rng.random() < P_PARCIAL else 0      # noqa: E731
    if score == 2:
        return [2]
    if score == 1:
        return [fallo(), 2]
    return [fallo(), fallo()]


def latencias(n: int, lpp: float, rng: np.random.Generator) -> list[int]:
    """n latencias con mediana exactamente igual a la LPP de la sesión."""
    x = rng.normal(lpp, 0.2 * lpp, n)
    x = x + (lpp - np.median(x))
    return [int(round(v)) for v in np.clip(x, 400, 9000)]


def reparto_palabras(n_validos: int, amlu: float, rng: np.random.Generator) -> list[int]:
    """Nº de palabras por turno válido, con media = aMLU (salvo redondeo) y algo de variación entre turnos."""
    if n_validos == 0:
        return []
    total = max(n_validos, int(round(amlu * n_validos)))
    base, resto = divmod(total, n_validos)
    w = [base + (1 if i < resto else 0) for i in range(n_validos)]
    for _ in range(n_validos):                                  # mueve palabras entre turnos sin cambiar el total
        i, j = rng.integers(0, n_validos, 2)
        if i != j and w[i] > 1:
            w[i] -= 1
            w[j] += 1
    rng.shuffle(w)
    return w


def texto_con_palabras(k: int, correcta: str, rng: np.random.Generator) -> str:
    """Texto de relleno con exactamente k palabras (según `metricas.palabras`), empezando por la respuesta esperada."""
    base = metricas._PALABRA.findall(correcta.split("/")[0].lower())
    extra = list(rng.choice(RELLENO, size=max(0, k - len(base))))
    texto = " ".join((base + extra)[:k])
    assert metricas.palabras(texto) == k
    return texto


# --------------------------------------------------------------------------- una sesión
def turnos_de_sesion(ses: dict, g: Guion, guiones: Guiones, conversacion_id: str,
                     rng: np.random.Generator) -> list[dict]:
    """Turnos (bot y menor) de una conversación sintética terminada, en orden."""
    n = len(g.turnos)
    n2, n1, n0 = composicion_figuras(ses["PEPE"], ses["pct_DET"], n)
    scores = [2] * n2 + [1] * n1 + [0] * n0
    rng.shuffle(scores)
    figuras = [(t, intentos_de_figura(s, rng)) for t, s in zip(g.turnos, scores)]

    # turnos del menor: apertura (no evaluada) + un turno por intento
    menor = [dict(nodo=nodo, tipo="apertura", intento=1, texto=txt, evaluacion=None, rama=rama)
             for nodo, rama, txt in APERTURA_MENOR]
    for t, evs in figuras:
        menor += [dict(nodo=t.id, tipo="competencia", intento=i, texto=None, evaluacion=ev, rama=None, _correcta=t.correcta)
                  for i, ev in enumerate(evs, start=1)]

    for m, lat in zip(menor, latencias(len(menor), ses["latencia_pragmatica_ms"], rng)):      # LPP
        m["latencia_ms"] = lat
    validos = [m for m in menor if m["evaluacion"] is not None and m["evaluacion"] >= 1]       # aMLU
    for m, k in zip(validos, reparto_palabras(len(validos), ses["aMLU"], rng)):
        m["texto"] = texto_con_palabras(k, m["_correcta"], rng)
    for m in menor:
        if m["texto"] is None:
            m["texto"] = str(rng.choice(FALLOS))

    # IRC: preguntas hasta llegar al nº de turnos con iniciativa de la sesión
    comp = g.competencia
    objetivo = int(round(ses["IRC_pct"] / 100 * len(menor)))
    sin_iniciativa = [m for m in menor if not metricas.iniciativa_turno(SimpleNamespace(**m), comp)]
    faltan = objetivo - (len(menor) - len(sin_iniciativa))
    for m in rng.permutation(len(sin_iniciativa))[:max(0, faltan)]:
        sin_iniciativa[m]["texto"] += "?"

    # intercalar los turnos del bot (texto literal del guion; la reacción del personaje es fija)
    ap = guiones.apertura
    filas = [dict(rol="bot", nodo="a1", tipo="apertura", intento=1,
                  texto=ap["a1"].format(nombre_usuario=ses["student_id"]))]
    siguiente_bot = {"a1": ("a2", "apertura", [ap["a2"]]),
                     "a2": (g.turnos[0].id, "competencia", [ap["rama_2B"], ap["cierre"], g.turnos[0].texto])}
    ids = [t.id for t in g.turnos]
    for m in menor:
        m.pop("_correcta", None)
        filas.append(dict(rol="menor", **m))
        if m["tipo"] == "apertura":
            nodo, tipo, msgs = siguiente_bot[m["nodo"]]
            filas.append(dict(rol="bot", nodo=nodo, tipo=tipo, intento=1, texto="\n".join(msgs)))
            continue
        reaccion = "¡Muy bien!" if m["evaluacion"] == 2 else "Gracias por intentarlo."
        turno = next(t for t in g.turnos if t.id == m["nodo"])
        if m["evaluacion"] < 2 and m["intento"] == 1:
            filas.append(dict(rol="bot", nodo=m["nodo"], tipo="competencia", intento=2, texto=f"{reaccion}\n{turno.ayuda}"))
        else:
            i = ids.index(m["nodo"])
            if i + 1 < len(ids):
                filas.append(dict(rol="bot", nodo=ids[i + 1], tipo="competencia", intento=1,
                                  texto=f"{reaccion}\n{g.turnos[i + 1].texto}"))
            else:
                filas.append(dict(rol="bot", nodo="fin", tipo="cierre", intento=1, texto=f"{reaccion}\n{g.cierre}"))

    for orden, f in enumerate(filas, start=1):
        f.update(conversacion_id=conversacion_id, orden=orden)
        f.setdefault("evaluacion", None)
        f.setdefault("rama", None)
        f.setdefault("latencia_ms", None)
        es_comp_menor = f["rol"] == "menor" and f["tipo"] == "competencia"
        f["evaluacion_origen"] = ORIGEN_EVALUACION if es_comp_menor else None
        f["evaluador_version"] = VERSION if es_comp_menor else None
        f["ayudas_solicitadas"] = 1 if es_comp_menor and f["intento"] > 1 else 0
        f["iniciativa"] = metricas.iniciativa_turno(SimpleNamespace(**f), comp) if f["rol"] == "menor" else None
        f["accuracy_corregido"] = None
    return filas


# --------------------------------------------------------------------------- corpus completo
def generar(train: pd.DataFrame, meta: pd.DataFrame, seed: int, guiones: Guiones | None = None
            ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(conversaciones, turnos) para todas las sesiones de `train` (salida del generador de Marcos)."""
    guiones = guiones or cargar_guiones()
    comp = meta.set_index("alumno_id")["competencia"]
    convs, turnos = [], []
    for idx, row in enumerate(train.sort_values(["alumno_id", "sesion"]).itertuples(index=False)):
        a, s = row.alumno_id, int(row.sesion)
        g = guiones.competencias[comp[a]]
        cid = str(uuid.uuid5(NS, f"conv-{a}-{s}"))
        ses = dict(row._asdict(), student_id=a)
        rng = np.random.default_rng([seed, int(a.split("-")[-1]), s])     # independiente del orden de las filas
        turnos += turnos_de_sesion(ses, g, guiones, cid, rng)
        convs.append(dict(conversacion_id=cid, session_id=str(uuid.uuid5(NS, f"{a}-{s}")), student_id=a, sesion_num=s,
                          competencia=g.competencia, personaje=g.personaje, alias=a, estado="terminada",
                          nodo_actual="fin", intento=1, guion_version=guiones.version, modelo=None,
                          es_prueba=True, origen="sintetico"))   # 013: sintética => de prueba (CHECK)
    cols = ["conversacion_id", "orden", "rol", "nodo", "tipo", "intento", "texto", "evaluacion", "evaluacion_origen",
            "rama", "latencia_ms", "evaluador_version", "iniciativa", "accuracy_corregido", "ayudas_solicitadas"]
    return pd.DataFrame(convs), pd.DataFrame(turnos)[cols]


def comprobar(train: pd.DataFrame, conversaciones: pd.DataFrame, turnos: pd.DataFrame) -> pd.DataFrame:
    """Recalcula las métricas desde los turnos con `app.metricas.calcular` y las compara con las de la sesión."""
    por_conv = {cid: [SimpleNamespace(**r) for r in df.to_dict("records")] for cid, df in turnos.groupby("conversacion_id")}
    t = train.set_index(["alumno_id", "sesion"])
    filas = []
    for c in conversaciones.itertuples(index=False):
        m = metricas.calcular(por_conv[c.conversacion_id], c.competencia)
        s = t.loc[(c.student_id, c.sesion_num)]
        n = len(cargar_guiones().competencias[c.competencia].turnos)
        filas.append(dict(student_id=c.student_id, sesion_num=c.sesion_num, competencia=c.competencia, n_figuras=n,
                          dif_PEPE=m.PEPE - s.PEPE, dif_LPP=m.latencia_pragmatica_ms - s.latencia_pragmatica_ms,
                          dif_aMLU=None if m.aMLU is None else m.aMLU - s.aMLU, dif_IRC=m.IRC_pct - s.IRC_pct,
                          pct_DET_sesion=s.pct_DET, pct_DET_observado_en_turnos=m.pct_DET_observado_en_turnos))
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------- base de datos (migración 013)
_SQL_CONV = """
    INSERT INTO conversacion (conversacion_id, student_id, competencia, personaje, alias, estado, nodo_actual, intento,
                              guion_version, modelo, es_prueba, origen)
    VALUES (CAST(:conversacion_id AS UUID), :student_id, :competencia, :personaje, :alias, :estado, :nodo_actual, :intento,
            :guion_version, :modelo, :es_prueba, :origen)
    ON CONFLICT (conversacion_id) DO NOTHING"""
_SQL_TURNO = """
    INSERT INTO conversacion_turno (conversacion_id, orden, rol, nodo, tipo, intento, texto, evaluacion, evaluacion_origen,
                                    rama, latencia_ms, evaluador_version, iniciativa, accuracy_corregido, ayudas_solicitadas)
    VALUES (CAST(:conversacion_id AS UUID), :orden, :rol, :nodo, :tipo, :intento, :texto, :evaluacion, :evaluacion_origen,
            :rama, :latencia_ms, :evaluador_version, :iniciativa, :accuracy_corregido, :ayudas_solicitadas)
    ON CONFLICT (conversacion_id, orden) DO NOTHING"""
_SQL_ENLACE = """
    UPDATE session_data SET conversacion_id = CAST(:conversacion_id AS UUID)
    WHERE session_id = CAST(:session_id AS UUID) AND origen = 'sintetico' AND conversacion_id IS NULL"""


def _py(v):
    """Valor de pandas/numpy -> tipo de Python para el driver (NaN -> None; 2.0 -> 2 en las columnas enteras)."""
    if v is None:
        return None
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float):
        if math.isnan(v):
            return None
        if v.is_integer():
            return int(v)
    return v


def _filas(df: pd.DataFrame) -> list[dict]:
    return [{k: _py(v) for k, v in r.items()} for r in df.to_dict("records")]


def insertar(db, conversaciones: pd.DataFrame, turnos: pd.DataFrame) -> tuple[int, int, int]:
    """Inserta conversaciones y turnos y enlaza cada sesión sintética con su conversación por `session_id`.

    `db` es una sesión o conexión de SQLAlchemy; no hace commit (lo hace quien llama). Idempotente: lo que ya existe no se
    duplica ni se reenlaza. Devuelve (conversaciones, filas de turno, sesiones enlazadas) de este corpus en la BD."""
    from sqlalchemy import text

    convs = _filas(conversaciones)
    if not convs:
        return 0, 0, 0
    db.execute(text(_SQL_CONV), [{k: c[k] for k in c if k not in ("session_id", "sesion_num")} for c in convs])
    db.execute(text(_SQL_TURNO), _filas(turnos))
    db.execute(text(_SQL_ENLACE), [{"conversacion_id": c["conversacion_id"], "session_id": c["session_id"]} for c in convs])
    ids = [c["conversacion_id"] for c in convs]
    n = db.execute(text(
        "SELECT (SELECT count(*) FROM conversacion WHERE conversacion_id = ANY(CAST(:ids AS UUID[]))),"
        "       (SELECT count(*) FROM conversacion_turno WHERE conversacion_id = ANY(CAST(:ids AS UUID[]))),"
        "       (SELECT count(*) FROM session_data WHERE conversacion_id = ANY(CAST(:ids AS UUID[])))"), {"ids": ids}).one()
    return int(n[0]), int(n[1]), int(n[2])


def sembrar(db, seed: int | None = None) -> tuple[int, int, int]:
    """Genera los turnos del corpus de Marcos (misma semilla que `seed_corpus`) y los carga con `insertar`."""
    from generador.generador_corpus_sintetico import cargar_config, generar_corpus

    cfg = cargar_config(SRC / "generador" / "config.yaml")
    seed = cfg["seed"] if seed is None else seed
    train, meta = generar_corpus(cfg, seed)
    conversaciones, turnos = generar(train, meta, seed)
    return insertar(db, conversaciones, turnos)


def main() -> None:
    from generador.generador_corpus_sintetico import cargar_config, generar_corpus

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seed", type=int, default=None, help="por defecto, la de config.yaml")
    p.add_argument("--out-dir", type=Path, default=Path("data/turnos_sinteticos"))
    args = p.parse_args()

    cfg = cargar_config(SRC / "generador" / "config.yaml")
    seed = cfg["seed"] if args.seed is None else args.seed
    train, meta = generar_corpus(cfg, seed)
    conversaciones, turnos = generar(train, meta, seed)
    comp = comprobar(train, conversaciones, turnos)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    conversaciones.to_csv(args.out_dir / "conversaciones_sinteticas.csv", index=False)
    turnos.to_csv(args.out_dir / "turnos_sinteticos.csv", index=False)
    comp.to_csv(args.out_dir / "comprobacion_metricas.csv", index=False)

    menor = turnos[turnos.rol == "menor"]
    print(f"Sesiones: {len(conversaciones)} · filas de turno: {len(turnos)} (menor: {len(menor)})")
    print(f"Eventos por figura (forma de turn_data): {menor.groupby(['conversacion_id', 'nodo']).ngroups}")
    print("Diferencia turnos -> sesión (valor absoluto):")
    for col in ("dif_PEPE", "dif_LPP", "dif_aMLU", "dif_IRC"):
        x = comp[col].dropna().abs()
        print(f"  {col:9s} mediana {x.median():.3f} · p95 {x.quantile(.95):.3f} · máx {x.max():.3f}"
              f" · sin valor {comp[col].isna().sum()}")


if __name__ == "__main__":
    main()
