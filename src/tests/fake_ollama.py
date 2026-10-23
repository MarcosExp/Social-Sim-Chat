"""Ollama simulado (httpx.MockTransport) para los tests de contrato."""
from __future__ import annotations

import json

import httpx


class FakeOllama:
    """Registra cada petición y responde según un guion de 'comportamientos'.

    `respuestas`: cola de evaluaciones a devolver en /api/chat (int 0/1/2 o dict/str crudo).
    `fallos`: cola de fallos previos a responder: "connect", "timeout", 500, 400, 404.
    """

    def __init__(self, modelo="qwen3:14b", modelos=("qwen3:14b",)):
        self.modelo, self.modelos = modelo, list(modelos)
        self.peticiones: list[dict] = []     # payloads de /api/chat
        self.respuestas: list = []
        self.fallos: list = []
        self.llamadas_chat = 0
        self.en_vuelo = 0
        self.max_en_vuelo = 0
        self.retardo_s = 0.0
        self.prompt_eval_count = 120
        self.caido = False

    def transport(self) -> httpx.MockTransport:
        import asyncio

        async def handler(req: httpx.Request) -> httpx.Response:
            if self.caido:
                raise httpx.ConnectError("simulado: conexión rechazada", request=req)
            if req.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": m, "model": m} for m in self.modelos]})
            if req.url.path == "/api/chat":
                self.llamadas_chat += 1
                self.peticiones.append(json.loads(req.content))
                if self.fallos:
                    f = self.fallos.pop(0)
                    if f == "connect":
                        raise httpx.ConnectError("simulado", request=req)
                    if f == "timeout":
                        raise httpx.ReadTimeout("simulado", request=req)
                    if f == 404:
                        return httpx.Response(404, json={"error": "model 'x' not found"})
                    return httpx.Response(f, text="error simulado")
                self.en_vuelo += 1
                self.max_en_vuelo = max(self.max_en_vuelo, self.en_vuelo)
                try:
                    if self.retardo_s:
                        await asyncio.sleep(self.retardo_s)
                finally:
                    self.en_vuelo -= 1
                r = self.respuestas.pop(0) if self.respuestas else 2
                if isinstance(r, int):
                    r = json.dumps({"evaluacion": r, "reaccion": "Gracias por contármelo, lo he entendido."})
                elif isinstance(r, dict):
                    r = json.dumps(r)
                return httpx.Response(200, json={
                    "model": self.modelo, "message": {"role": "assistant", "content": r},
                    "prompt_eval_count": self.prompt_eval_count, "eval_count": 25,
                    "total_duration": 900_000_000, "load_duration": 5_000_000})
            return httpx.Response(404, text="not found")

        return httpx.MockTransport(handler)
