#!/usr/bin/env python3
"""Batería de regresión del prompt de valoración 0/1/2 (OPCIONAL: necesita el Ollama real).

    python -m scripts.bateria_valoracion                       # baterías 1, 2 y 3, sin y con historial
    python -m scripts.bateria_valoracion --bateria 2 --historial con --repeticiones 3 --detalle
    python -m scripts.bateria_valoracion --bateria 3 --repeticiones 3 --ocultar-fallos   # solo para MEDIR (examen)
    make bateria                                               # equivalente en el contenedor

Cada caso es una respuesta del «menor» a un nodo del guion con el conjunto de valoraciones aceptables:
  - buena      -> [2]
  - mala       -> [0]            (literal, opuesta, eco, evasiva, fuera de tema, vacía, sin sentido, inyección)
  - fronteriza -> [1, 2] o [0, 1] (no se exige una nota concreta, solo que no caiga en el extremo equivocado)
Datos en src/tests/data/bateria_valoracion_{1,2,3,4}.json.

  Batería 1: las 88 respuestas con las que se AFINÓ el primer prompt (regresión; sobreajustada por construcción).
  Batería 2: frases y tipos de error distintos; sirvió de DESARROLLO del segundo prompt.
  Batería 3: ~100 respuestas escritas por gpt-oss:20b (otra familia que el evaluador). NO se usa para afinar: solo para
             medir el resultado final. Sus etiquetas las revisa un humano (campo `revisada_por_humano`).

  Batería 4: 104 respuestas escritas por Claude el 25/10/2026 SIN consultar las reglas del modo simulado y antes de medirlas;
             es el examen del modo `LLM_PROVIDER=simulado` (se ejecutó una vez con las reglas congeladas). Etiquetas sin revisar.

Se valora como en producción: primero la guarda de inyecciones en código y, si no salta, el LLM (`--sin-guarda` mide el LLM
solo). Métricas: buenas con 2, falsos 2 (mala valorada 2), sobrevaloración 1, fronterizas dentro de lo aceptable y mediana de
tiempo por turno con LLM. Salida 0 si se cumplen los umbrales, 1 si no, 2 si Ollama no responde.
El LLM no es determinista (temperatura 0,2): usa --repeticiones 3 para ver la dispersión.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

from app import conversacion as cv
from app import llm_client
from app.config import settings
from app.guiones import cargar_guiones

DATOS = Path(__file__).resolve().parent.parent / "tests" / "data"
# Umbrales de regresión (miden que el prompt NO EMPEORA; los objetivos de calidad están en el informe de validación §10).
# Referencia 2026-10-12 con el prompt p3 + guarda (por pasada, 3 repeticiones): batería 1 → 1/75 falsos 2 y 13/13 buenas;
# batería 2 → 1/71 y 24/27; batería 3 → 0-1/52 y 23/26. Los umbrales dejan margen por el ruido del modelo (temperatura 0,2).
# Referencia 2026-10-25 (código de las seis PR, mismo modelo, 3 repeticiones, con historial): batería 3 → 0/52 y 23/26; batería 4 → 2/52 y 26/26.
# Las referencias de la batería 3 son anteriores a la revisión del 27/10/2026 (entonces 26 buenas y 52 malas; ahora 23 y 53): sus umbrales con el LLM real están sin remedir.
# Los umbrales y las referencias son de `qwen3:14b`: con otro modelo hay que remedirlos. El 26/10/2026, `openai` por TabbyAPI con Qwen3-Coder-30B-A3B
# (EXL3 3,34 bpw) dio de media 6,3 falsos 2 por pasada en la batería 3 con historial (19/156) y 2,7 en la 4 (8/156), y el script salió con código 1.
UMBRALES = {
    "1": {"max_falsos2": 3, "min_buenas": 12},
    "2": {"max_falsos2": 3, "min_buenas": 22},
    "3": {"max_falsos2": 3, "min_buenas": 21},
    "4": {"max_falsos2": 3, "min_buenas": 21},       # medida con el LLM real el 25/10/2026 (2-3 falsos 2 y 26 buenas por pasada): cabe, se deja igual
}
# Con `LLM_PROVIDER=simulado` (LLM falso por reglas, docs/modo-simulado.md) se aplican ESTOS, no los del LLM: son los resultados de
# hoy (también de NO EMPEORAR, no objetivos). La batería 3 queda por encima de los umbrales del LLM (5 falsos 2 > 3) y eso no
# debe hacer fallar `make bateria` en el modo simulado. Las baterías 1-3 son de desarrollo; la 4 es el examen a ciegas.
UMBRALES_SIMULADO = {
    "1": {"max_falsos2": 0, "min_buenas": 12},
    "2": {"max_falsos2": 0, "min_buenas": 26},
    "3": {"max_falsos2": 5, "min_buenas": 22},     # 27/10/2026: tras la revisión humana la 3 tiene 23 buenas (antes 26); simulado da 22/23 y 3/53
    "4": {"max_falsos2": 1, "min_buenas": 21},
}


def cargar(n: str) -> list[dict]:
    return json.loads((DATOS / f"bateria_valoracion_{n}.json").read_text(encoding="utf-8"))["casos"]


def _nodos():
    G = cargar_guiones()
    out = {}
    for g in G.competencias.values():
        for t in g.turnos:
            out[t.id] = (g, t)
    return G, out


async def valorar(G, g, turno, respuesta: str, con_historial: bool, con_guarda: bool = True):
    """(evaluacion, ms_llm | None, patrones): `ms_llm` es None cuando salta la guarda (no se llamó al modelo)."""
    prev = []
    if con_historial:  # lo que ve el modelo en un turno real: el mensaje previo del bot en el mismo nodo
        prev = [SimpleNamespace(rol="bot", nodo=turno.id,
                                texto="Gracias por tu respuesta. Vamos a seguir jugando juntos.\n" + turno.texto)]
    conv = SimpleNamespace(turnos=prev)
    if con_guarda:
        ev, _, res, _, patrones = await cv.valorar(conv, G, g, turno, respuesta)
    else:
        ev, _, res = await cv.evaluar_con_llm(conv, G, g, turno, respuesta)
        patrones = []
    return ev, (res.ms_total if res is not None else None), patrones


async def ejecutar(n: str, con_historial: bool, repeticiones: int, con_guarda: bool) -> dict:
    G, nodos = _nodos()
    casos = cargar(n)
    res = {"n": n, "historial": con_historial, "guarda": con_guarda, "repeticiones": repeticiones, "casos": len(casos),
           "malas": 0, "falsos2": 0, "sobre1": 0, "buenas": 0, "buenas_ok": 0, "front": 0, "front_ok": 0,
           "por_tipo": defaultdict(Counter), "fallos": [], "ms": [], "guarda_saltos": 0}
    for c in casos:
        g, turno = nodos[c["nodo"]]
        for _ in range(repeticiones):
            ev, ms, patrones = await valorar(G, g, turno, c["respuesta"], con_historial, con_guarda)
            if ms is not None:
                res["ms"].append(ms)
            res["guarda_saltos"] += bool(patrones)
            esp, tipo = c["esperado"], c["tipo"]
            ok = ev in esp
            res["por_tipo"][tipo]["total"] += 1
            res["por_tipo"][tipo]["ok"] += ok
            if esp == [2]:
                res["buenas"] += 1; res["buenas_ok"] += ok
            elif esp == [0]:
                res["malas"] += 1
                res["falsos2"] += ev == 2
                res["sobre1"] += ev == 1
            else:
                res["front"] += 1; res["front_ok"] += ok
            if not ok:
                res["fallos"].append((c["nodo"], tipo, c["respuesta"], esp, ev))
    return res


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.1f} %)" if b else "—"


def imprimir(r: dict, detalle: bool, ocultar_fallos: bool) -> None:
    h = "con historial" if r["historial"] else "sin historial"
    ev = "LLM falso (simulado)" if settings.llm_simulado else "LLM"
    g = f"guarda + {ev}" if r["guarda"] else f"{ev} solo"
    print(f"\n[batería {r['n']} · {h} · {g} · {r['repeticiones']} rep. · {r['casos']} casos]")
    print(f"  buenas valoradas 2:           {pct(r['buenas_ok'], r['buenas'])}")
    print(f"  malas valoradas 2 (falsos 2): {pct(r['falsos2'], r['malas'])}")
    print(f"  malas valoradas 1 (sobre 1):  {pct(r['sobre1'], r['malas'])}")
    if r["front"]:
        print(f"  fronterizas dentro de lo aceptable: {pct(r['front_ok'], r['front'])}")
    if r["ms"]:
        print(f"  tiempo por turno con LLM: mediana {statistics.median(r['ms']) / 1000:.2f} s · p90 "
              f"{sorted(r['ms'])[int(0.9 * len(r['ms']))] / 1000:.2f} s · llamadas {len(r['ms'])}")
    if r["guarda"]:
        print(f"  saltos de la guarda: {r['guarda_saltos']} de {r['casos'] * r['repeticiones']} valoraciones")
    if detalle:
        print("  por tipo (acierto/total):", ", ".join(f"{t} {c['ok']}/{c['total']}" for t, c in sorted(r["por_tipo"].items())))
    if ocultar_fallos:
        return
    for nodo, tipo, resp, esp, ev in r["fallos"]:
        print(f"    ✗ {nodo} [{tipo}] {resp[:60]!r}: esperado {esp}, dio {ev}")


async def main_async(a) -> int:
    try:
        h = await llm_client.check_llm_health()
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Ollama no responde: {exc}")
        return 2
    if h != "ok":
        print(f"✗ Ollama no está listo: {h}")
        return 2
    mal, salida = 0, []
    for n in (["1", "2", "3", "4"] if a.bateria == "todas" else [a.bateria]):
        for con in ({"sin": [False], "con": [True], "ambos": [False, True]}[a.historial]):
            r = await ejecutar(n, con, a.repeticiones, not a.sin_guarda)
            imprimir(r, a.detalle, a.ocultar_fallos)
            salida.append({k: v for k, v in r.items() if k not in ("fallos", "ms", "por_tipo")} |
                          {"mediana_ms": statistics.median(r["ms"]) if r["ms"] else None,
                           "por_tipo": {t: dict(c) for t, c in r["por_tipo"].items()}})
            u = (UMBRALES_SIMULADO if settings.llm_simulado else UMBRALES)[n]
            if r["falsos2"] > u["max_falsos2"] * a.repeticiones or r["buenas_ok"] < u["min_buenas"] * a.repeticiones:
                print(f"  → FUERA de umbral (falsos 2 ≤ {u['max_falsos2']}, buenas ≥ {u['min_buenas']} por pasada"
                      f"{'; umbrales del modo simulado' if settings.llm_simulado else ''})")
                mal += 1
    if a.json:
        Path(a.json).write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if mal else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bateria", choices=["1", "2", "3", "4", "todas"], default="todas")
    ap.add_argument("--historial", choices=["sin", "con", "ambos"], default="ambos")
    ap.add_argument("--repeticiones", type=int, default=1)
    ap.add_argument("--detalle", action="store_true", help="acierto por tipo de respuesta")
    ap.add_argument("--sin-guarda", action="store_true", help="medir el LLM solo, sin la guarda de inyecciones")
    ap.add_argument("--ocultar-fallos", action="store_true", help="no listar los casos fallados (batería 3: solo se mide)")
    ap.add_argument("--json", help="guarda el resumen en este fichero")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
