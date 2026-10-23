#!/usr/bin/env python3
"""API simulada SOLO para probar la pantalla /chat sin Docker, Postgres ni Ollama.

Imita el contrato de docs/api-conversacion.md (GET /students, POST /conversaciones, POST /conversaciones/{id}/turnos,
GET /health) y sirve la pantalla en /chat/. Sin dependencias (solo biblioteca estándar).

    python -m scripts.mock_api_chat --puerto 8099
    -> http://127.0.0.1:8099/chat/

Comportamientos para probar la pantalla:
  - un mensaje que contenga «fallo503» devuelve 503 reintentable la primera vez (la segunda vez funciona);
  - «fallo409» devuelve 409 conversacion_terminada;
  - «fallo422» devuelve 422 no reintentable;
  - tras 3 turnos de competencia la conversación termina (estado «terminada»).
GET /_debug/turnos devuelve los turnos recibidos (con latencia_ms) para las pruebas automáticas.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ESTATICOS = Path(__file__).resolve().parent.parent / "app" / "static" / "chat"
ALUMNOS = [
    {"student_id": "sim-001", "competencia_objetivo": "Metáfora"},
    {"student_id": "sim-002", "competencia_objetivo": "Sarcasmo"},
]
FIGURAS = ["Mona no va a explotar de verdad. ¿Qué quiere decir?", "¿Qué significa «pan comido»?", "¿Y «se me heló la sangre»?"]
CONVERSACIONES: dict[str, dict] = {}
TURNOS_RECIBIDOS: list[dict] = []
FALLOS_USADOS: set[str] = set()


def _turno_bot(personaje: str, mensajes: list[str], nodo: str = "M1") -> dict:
    return {"nodo": nodo, "tipo": "competencia", "personaje": personaje, "mensajes": mensajes, "texto": "\n".join(mensajes)}


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencio
        pass

    def _json(self, status: int, cuerpo, cabeceras: dict | None = None):
        datos = json.dumps(cuerpo, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        for k, v in (cabeceras or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(datos)

    def _cuerpo(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        ruta = self.path.split("?")[0]
        if ruta == "/students":
            return self._json(200, ALUMNOS)
        if ruta == "/health":
            return self._json(200, {"status": "ok", "database": "ok", "llm_provider": "mock", "llm": "ok"})
        if ruta == "/_debug/turnos":
            return self._json(200, TURNOS_RECIBIDOS)
        if ruta in ("/chat", "/chat/"):
            ruta = "/chat/index.html"
        if ruta.startswith("/chat/"):
            f = (ESTATICOS / ruta[len("/chat/"):]).resolve()
            if ESTATICOS in f.parents and f.is_file():
                datos = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", (mimetypes.guess_type(f.name)[0] or "application/octet-stream") + "; charset=utf-8")
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)
                return
        self._json(404, {"codigo": "no_encontrado", "mensaje": "No existe.", "reintentable": False})

    def do_POST(self):
        ruta = self.path.split("?")[0]
        cuerpo = self._cuerpo()
        if ruta == "/conversaciones":
            alumno = next((a for a in ALUMNOS if a["student_id"] == cuerpo.get("student_id")), None)
            if alumno is None:
                return self._json(404, {"codigo": "alumno_no_encontrado", "mensaje": "No existe el alumno.", "reintentable": False})
            cid = str(uuid.uuid4())
            comp = cuerpo.get("competencia") or alumno["competencia_objetivo"]
            alias = cuerpo.get("alias") or alumno["student_id"]
            CONVERSACIONES[cid] = {"turnos": 0, "personaje": "Mona", "competencia": comp}
            return self._json(201, {
                "conversacion_id": cid, "student_id": alumno["student_id"], "competencia": comp, "personaje": "Mona",
                "estado": "en_curso", "nodo_actual": "a1", "intento": 1, "guion_version": "mock",
                "turno_bot": _turno_bot("Mona", [f"¡Hola {alias}! Qué bien verte por aquí otra vez. ¿Cómo estás hoy?"], "a1")})
        partes = ruta.strip("/").split("/")
        if len(partes) == 3 and partes[0] == "conversaciones" and partes[2] == "turnos":
            c = CONVERSACIONES.get(partes[1])
            if c is None:
                return self._json(404, {"codigo": "conversacion_no_encontrada", "mensaje": "No existe.", "reintentable": False})
            msg = cuerpo.get("mensaje", "")
            if not (1 <= len(msg.strip()) <= 500):
                return self._json(422, {"codigo": "validacion", "mensaje": "El mensaje debe tener entre 1 y 500 caracteres.", "reintentable": False})
            if "fallo503" in msg and "503" not in FALLOS_USADOS:
                FALLOS_USADOS.add("503")
                return self._json(503, {"codigo": "llm_no_disponible", "mensaje": "Ollama no responde.", "reintentable": True}, {"Retry-After": "1"})
            if "fallo409" in msg:
                return self._json(409, {"codigo": "conversacion_terminada", "mensaje": "La conversación ya terminó.", "reintentable": False})
            if "fallo422" in msg:
                return self._json(422, {"codigo": "validacion", "mensaje": "Mensaje no válido.", "reintentable": False})
            TURNOS_RECIBIDOS.append({"mensaje": msg, "latencia_ms": cuerpo.get("latencia_ms")})
            c["turnos"] += 1
            if c["turnos"] > len(FIGURAS):
                estado, bot = "terminada", _turno_bot(c["personaje"], ["¡Muy bien! Hemos terminado por hoy."], "fin")
            else:
                estado = "en_curso"
                bot = _turno_bot(c["personaje"], ["Gracias por tu respuesta.", FIGURAS[c["turnos"] - 1]], f"M{c['turnos']}")
            return self._json(200, {
                "conversacion_id": partes[1], "student_id": "sim-001", "competencia": c["competencia"], "personaje": c["personaje"],
                "estado": estado, "nodo_actual": bot["nodo"], "intento": 1, "guion_version": "mock", "turno_bot": bot,
                "evaluacion": 2, "evaluacion_origen": "llm", "latencia_ms": cuerpo.get("latencia_ms")})
        self._json(404, {"codigo": "no_encontrado", "mensaje": "No existe.", "reintentable": False})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puerto", type=int, default=8099)
    a = ap.parse_args()
    s = ThreadingHTTPServer(("127.0.0.1", a.puerto), Manejador)
    print(f"API simulada en http://127.0.0.1:{a.puerto}/chat/  (Ctrl+C para parar)")
    s.serve_forever()


if __name__ == "__main__":
    main()
