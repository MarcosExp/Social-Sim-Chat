#!/usr/bin/env python3
"""Prueba de humo REAL: recorre una conversación completa contra el backend (y por tanto contra Ollama)
y mide la latencia de cada turno.

    python -m scripts.smoke_conversacion                       # backend en http://localhost:8010
    python -m scripts.smoke_conversacion --competencia Sarcasmo --max-p50 8 --max-turno 30

Qué mide:
  - /health antes de empezar (falla con el mensaje accionable si Ollama no está listo).
  - Por turno: tiempo total de la petición HTTP y desglose que devuelve la API (`llm.ollama_ms`,
    `llm.carga_ms`, `llm.espera_cola_ms`, `llm.prompt_tokens`).
  - Primer turno con LLM = arranque en frío (si el modelo no estaba en VRAM, incluye su carga);
    el resto = régimen "caliente". Se informan por separado.
Código de salida 0 si todo cabe en los umbrales, 1 si se superan, 2 si el entorno no está listo.
Crea una conversación en la BD marcada como de prueba (`es_prueba`): no genera sesión real ni métricas.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

import httpx

# Respuestas del "menor" en orden; mezcla acierto/literal para ejercitar ayuda y avance.
RESPUESTAS_APERTURA = ["hola", "sí, vale", ]
RESPUESTAS_COMPETENCIA = [
    "Quiere decir que está muy nervioso, como si tuviera mariposas en la tripa",
    "no sé",
    "que se ha ido a otro sitio",
    "es una forma de hablar, no es de verdad",
    "tiene mucha hambre",
    "pues que se enfada",
]


def pedir(c: httpx.Client, metodo: str, url: str, **kw):
    t0 = time.perf_counter()
    r = c.request(metodo, url, **kw)
    return r, (time.perf_counter() - t0) * 1000


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.getenv("BACKEND_URL", "http://localhost:8010"))
    ap.add_argument("--student", help="student_id existente (por defecto, el primero de /students)")
    ap.add_argument("--competencia", help="por defecto, la competencia objetivo del alumno")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--max-p50", type=float, default=10.0, help="umbral de mediana por turno con LLM (s)")
    ap.add_argument("--max-turno", type=float, default=60.0, help="umbral del peor turno (s), incluida carga en frío")
    ap.add_argument("--json", dest="salida", help="guarda el informe en este fichero")
    ap.add_argument("--api-key", default=os.getenv("API_KEY_TERAPEUTA"),
                    help="clave de la API del terapeuta (cabecera X-API-Key; por defecto, la variable API_KEY_TERAPEUTA)")
    a = ap.parse_args()

    cabeceras = {"X-API-Key": a.api_key} if a.api_key else {}
    with httpx.Client(base_url=a.url, timeout=a.timeout, headers=cabeceras) as c:
        try:
            h = c.get("/health", timeout=10).json()
        except httpx.HTTPError as exc:
            print(f"✗ El backend no responde en {a.url}: {exc}\n  ¿Está levantado? (docker compose ... up -d)")
            return 2
        print(f"/health: status={h['status']} db={h['database']} llm={h['llm']} modelo={h.get('llm_model')}")
        if h["llm"] != "ok":
            print("✗ El motor LLM no está listo; no tiene sentido medir. Arréglalo con el mensaje de arriba.")
            return 2

        if not a.student:
            r = c.get("/students")
            if r.status_code in (401, 403):
                print("✗ /students exige la clave del terapeuta: define API_KEY_TERAPEUTA o usa --api-key, o pasa --student.")
                return 2
            sid = r.json()[0]["student_id"]
        else:
            sid = a.student
        body = {"student_id": sid, "prueba": True, **({"competencia": a.competencia} if a.competencia else {})}
        r, _ = pedir(c, "POST", "/conversaciones", json=body)
        if r.status_code != 201:
            print(f"✗ No se pudo crear la conversación: {r.status_code} {r.text}")
            return 2
        conv = r.json()
        cid = conv["conversacion_id"]
        print(f"Conversación {cid} · {conv['competencia']} con {conv['personaje']} · alumno {sid}\n")
        print(f"{'#':>2} {'nodo':<5} {'eval':>4} {'total s':>8} {'ollama s':>9} {'carga s':>8} {'cola s':>7} {'tok in':>7}  respuesta del bot")

        filas, n = [], 0
        while conv["estado"] == "en_curso" and n < 40:
            n += 1
            msg = (RESPUESTAS_APERTURA[n - 1] if n <= len(RESPUESTAS_APERTURA)
                   else RESPUESTAS_COMPETENCIA[(n - len(RESPUESTAS_APERTURA) - 1) % len(RESPUESTAS_COMPETENCIA)])
            r, ms = pedir(c, "POST", f"/conversaciones/{cid}/turnos", json={"mensaje": msg})
            if r.status_code != 200:
                print(f"✗ Turno {n}: HTTP {r.status_code} {r.text}")
                return 2 if r.status_code == 503 else 1
            conv = r.json()
            llm = conv.get("llm")
            filas.append({"turno": n, "nodo": conv["nodo_actual"], "evaluacion": conv.get("evaluacion"),
                          "total_ms": round(ms), "llm": llm})
            f = lambda k: f"{llm[k] / 1000:.2f}" if llm and llm.get(k) is not None else "-"  # noqa: E731
            print(f"{n:>2} {conv['nodo_actual']:<5} {str(conv.get('evaluacion') if llm else '-'):>4} {ms / 1000:>8.2f} "
                  f"{f('ollama_ms'):>9} {f('carga_ms'):>8} {f('espera_cola_ms'):>7} "
                  f"{(llm or {}).get('prompt_tokens', '-'):>7}  {conv['turno_bot']['texto'][:60]!r}")

        con_llm = [x for x in filas if x["llm"]]
        sin_llm = [x for x in filas if not x["llm"]]
        informe = {"conversacion_id": cid, "estado_final": conv["estado"], "turnos": filas,
                   "modelo": (con_llm[0]["llm"]["modelo"] if con_llm else None)}
        print()
        if not con_llm:
            print("✗ Ningún turno llegó al LLM (¿la conversación quedó en la apertura?).")
            return 1
        frio = con_llm[0]["total_ms"] / 1000
        caliente = [x["total_ms"] / 1000 for x in con_llm[1:]] or [frio]
        p50, peor = statistics.median(caliente), max(x["total_ms"] for x in con_llm) / 1000
        cargado = (con_llm[0]["llm"].get("carga_ms") or 0) > 1000
        print(f"Turnos sin LLM (apertura): {len(sin_llm)} · con LLM: {len(con_llm)} · estado final: {conv['estado']}")
        print(f"Primer turno con LLM: {frio:.2f} s{' (incluye carga del modelo en VRAM)' if cargado else ''}")
        print(f"Régimen caliente: mediana {p50:.2f} s · máx {max(caliente):.2f} s · peor turno global {peor:.2f} s")
        informe |= {"frio_s": round(frio, 2), "p50_caliente_s": round(p50, 2), "peor_s": round(peor, 2)}
        if a.salida:
            with open(a.salida, "w", encoding="utf-8") as fh:
                json.dump(informe, fh, ensure_ascii=False, indent=2)
        ok = True
        if conv["estado"] != "terminada":
            print("✗ La conversación no llegó al cierre.")
            ok = False
        if p50 > a.max_p50:
            print(f"✗ Mediana {p50:.1f} s > umbral {a.max_p50:g} s (para un niño esperar tanto rompe el ritmo del turno).")
            ok = False
        if peor > a.max_turno:
            print(f"✗ Peor turno {peor:.1f} s > umbral {a.max_turno:g} s.")
            ok = False
        print("✓ Prueba de humo superada." if ok else "")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
