"""Ollama simulado (httpx.MockTransport) para los tests de contrato.

Sirve la API nativa (/api/tags, /api/chat) y la compatible con OpenAI (/v1/models, /v1/chat/completions) con la misma
cola de `respuestas` y `fallos`, para probar que se puede cambiar de proveedor sin tocar el resto del sistema.
"""
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
        self.peticiones: list[dict] = []     # payloads de /api/chat o /v1/chat/completions
        self.cabeceras: list[dict] = []      # cabeceras de cada petición de chat
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
            if req.url.path == "/v1/models":
                return httpx.Response(200, json={"object": "list", "data": [{"id": m, "object": "model"} for m in self.modelos]})
            if req.url.path in ("/api/chat", "/v1/chat/completions"):
                compat = req.url.path.startswith("/v1")
                self.llamadas_chat += 1
                self.peticiones.append(json.loads(req.content))
                self.cabeceras.append(dict(req.headers))
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
                if compat:
                    return httpx.Response(200, json={
                        "model": self.modelo, "choices": [{"index": 0, "message": {"role": "assistant", "content": r}}],
                        "usage": {"prompt_tokens": self.prompt_eval_count, "completion_tokens": 25}})
                return httpx.Response(200, json={
                    "model": self.modelo, "message": {"role": "assistant", "content": r},
                    "prompt_eval_count": self.prompt_eval_count, "eval_count": 25,
                    "total_duration": 900_000_000, "load_duration": 5_000_000})
            return httpx.Response(404, text="not found")

        return httpx.MockTransport(handler)
