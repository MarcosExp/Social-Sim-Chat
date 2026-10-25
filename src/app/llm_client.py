"""Cliente del motor conversacional (LLM local).

Proveedores (LLM_PROVIDER, ver app.config):

- "ollama":   Ollama del host (por defecto http://host.docker.internal:11434) o el servicio
              opcional `ollama` del compose. Se usa la API nativa (/api/chat) porque permite
              `think: false` (qwen3 razona por defecto) y `keep_alive`.
- "openai":   cualquier servidor con API compatible con OpenAI (/v1/chat/completions): el /v1 de
              Ollama, vLLM, LM Studio, TabbyAPI... Es la interfaz que fija NF2 para poder sustituir el
              motor local sin tocar el resto del sistema. Envía `max_tokens` y, para el evaluador,
              `response_format` json_schema; no controla `think` (se retiran los bloques <think>).
- "tabbyapi": alias histórico de "openai" con las variables TABBYAPI_* (sin response_format).

Garantías de este cliente (pensadas para 16 GB de VRAM y un único modelo cargado):

1. `num_ctx` SIEMPRE explícito. Con el valor por defecto de Ollama el prompt se trunca en
   silencio; aquí, si el prompt estimado no cabe, se lanza `ContextoExcedido` antes de enviar.
2. `think: false`, `stream: false` y `keep_alive` largo en cada petición.
3. UNA petición a la vez por proceso (semáforo): las conversaciones se serializan. Si la cola
   no se libera en `ollama_cola_timeout_s`, `LLMOcupado`. Requiere un solo worker de uvicorn.
4. Reintento acotado (`ollama_max_reintentos`, espera exponencial) solo ante fallos de conexión,
   timeouts y 5xx. Agotados, `LLMNoDisponible` con un mensaje accionable. Los 4xx no se reintentan.
5. `diagnostico_llm()` da un estado claro para /health, sin pasar por la cola ni reintentar.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import weakref
from dataclasses import dataclass

import httpx

from app.config import settings


# ----------------------------------------------------------------------------- errores
class LLMError(Exception):
    codigo = "llm_error"
    reintentable = False

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class LLMNoDisponible(LLMError):
    codigo = "llm_no_disponible"
    reintentable = True


class LLMOcupado(LLMError):
    codigo = "llm_ocupado"
    reintentable = True


class ModeloNoEncontrado(LLMError):
    codigo = "modelo_no_encontrado"


class ContextoExcedido(LLMError):
    codigo = "contexto_excedido"


class RespuestaInvalida(LLMError):
    codigo = "respuesta_invalida"
    reintentable = True


# ----------------------------------------------------------------------------- infraestructura
_TRANSPORT: httpx.AsyncBaseTransport | None = None  # los tests inyectan aquí un servidor simulado
_COLAS: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def _cliente(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=_TRANSPORT)


def _cola() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _COLAS.get(loop)
    if sem is None:
        sem = _COLAS[loop] = asyncio.Semaphore(1)
    return sem


def _headers() -> dict[str, str]:
    if settings.llm_provider == "tabbyapi" and settings.tabbyapi_api_key:
        return {"x-api-key": settings.tabbyapi_api_key}
    if settings.llm_provider == "openai" and settings.llm_compat_api_key:
        return {"Authorization": f"Bearer {settings.llm_compat_api_key}"}
    return {}


def estimar_tokens(messages: list[dict]) -> int:
    """Estimación conservadora (~3 caracteres por token en español) + sobrecoste por mensaje."""
    return sum(len(m.get("content", "")) // 3 + 8 for m in messages)


@dataclass
class ChatResultado:
    texto: str
    modelo: str
    prompt_tokens: int | None
    eval_tokens: int | None
    ollama_ms: int | None      # total_duration que informa Ollama
    carga_ms: int | None       # load_duration: >0 si hubo que cargar el modelo
    espera_cola_ms: int        # tiempo esperando turno (conversaciones serializadas)
    intentos: int
    ms_total: int              # reloj de pared de la llamada completa (cola + reintentos)


# ----------------------------------------------------------------------------- diagnóstico
async def diagnostico_llm(timeout: float = 3.0) -> dict:
    """Estado del proveedor para /health: {estado, detalle, modelo, modelo_disponible}."""
    if settings.llm_simulado:
        from app import simulado
        return simulado.diagnostico()
    base = settings.llm_base_url.rstrip("/")
    modelo = settings.llm_model
    out = {"estado": "error", "detalle": "", "modelo": modelo, "modelo_disponible": None}
    path = "/api/tags" if settings.llm_provider == "ollama" else "/v1/models"
    try:
        async with _cliente(timeout) as c:
            r = await c.get(f"{base}{path}", headers=_headers())
            r.raise_for_status()
            data = r.json()
    except httpx.ConnectError:
        out["detalle"] = (f"no se puede conectar con {settings.llm_provider} en {base}. "
                          "¿Está arrancado? Con Ollama en el host Windows hace falta OLLAMA_HOST=0.0.0.0 "
                          "y que el contenedor llegue a host.docker.internal.")
        return out
    except httpx.TimeoutException:
        out["detalle"] = f"{settings.llm_provider} en {base} no responde en {timeout:g} s."
        return out
    except httpx.HTTPStatusError as exc:
        out["detalle"] = f"{settings.llm_provider} en {base} respondió HTTP {exc.response.status_code}."
        return out
    except Exception as exc:  # noqa: BLE001
        out["detalle"] = f"{type(exc).__name__}: {exc}"
        return out

    if settings.llm_provider == "ollama":
        nombres = {m.get("name") for m in data.get("models", [])} | {m.get("model") for m in data.get("models", [])}
        disponible = modelo in nombres or f"{modelo}:latest" in nombres
        out["modelo_disponible"] = disponible
        if not disponible:
            out["detalle"] = f"Ollama responde, pero el modelo '{modelo}' no está instalado. Ejecuta: ollama pull {modelo}"
            return out
    elif settings.llm_provider == "openai":
        ids = {m.get("id") for m in (data.get("data") or [])}
        disponible = modelo in ids or f"{modelo}:latest" in ids
        out["modelo_disponible"] = disponible
        if not disponible:
            out["detalle"] = (f"El servidor responde, pero el modelo '{modelo}' no aparece en /v1/models. "
                              "Revisa LLM_COMPAT_MODEL o carga el modelo en el servidor.")
            return out
    out["estado"], out["detalle"] = "ok", "ok"
    return out


async def check_llm_health(timeout: float = 3.0) -> str:
    """Compatibilidad: 'ok' o 'error: ...'."""
    d = await diagnostico_llm(timeout)
    return "ok" if d["estado"] == "ok" else f"error: {d['detalle']}"


# ----------------------------------------------------------------------------- chat
def _payload_ollama(messages, formato, temperature, num_predict) -> dict:
    p = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": False,
        "think": settings.ollama_think,
        "keep_alive": settings.ollama_keep_alive,
        "options": {
            "num_ctx": settings.ollama_num_ctx,
            "temperature": settings.ollama_temperature if temperature is None else temperature,
            "num_predict": settings.ollama_num_predict if num_predict is None else num_predict,
        },
    }
    if formato is not None:
        p["format"] = formato
    return p


def _payload_openai(messages, formato, temperature, num_predict) -> dict:
    p = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": False,
        "temperature": settings.ollama_temperature if temperature is None else temperature,
        "max_tokens": settings.ollama_num_predict if num_predict is None else num_predict,
    }
    if isinstance(formato, dict) and settings.llm_provider == "openai" and settings.llm_compat_response_format:
        schema = {"additionalProperties": False, **formato}   # copia: SCHEMA_EVALUACION entra en la huella del evaluador
        p["response_format"] = {"type": "json_schema", "json_schema": {"name": "respuesta", "strict": True, "schema": schema}}
    return p


def _sin_razonamiento(texto: str) -> str:
    """Quita los bloques <think>...</think> que algunos modelos (qwen3) emiten si el servidor no los separa."""
    return re.sub(r"<think>.*?</think>", "", texto, flags=re.S).strip()


async def _post_con_reintentos(client: httpx.AsyncClient, url: str, payload: dict) -> tuple[dict, int]:
    max_r = max(0, settings.ollama_max_reintentos)
    ultimo: Exception | None = None
    for intento in range(1, max_r + 2):
        try:
            r = await client.post(url, json=payload, headers=_headers())
            if r.status_code >= 500:
                raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            if r.status_code == 404 and "not found" in r.text.lower():
                accion = (f"Ejecuta: ollama pull {settings.llm_model}" if settings.llm_provider == "ollama"
                          else "Revisa el nombre del modelo y que esté cargado en el servidor.")
                raise ModeloNoEncontrado(f"El modelo '{settings.llm_model}' no está en el proveedor. {accion}")
            if r.status_code >= 400:
                raise LLMError(f"El proveedor rechazó la petición (HTTP {r.status_code}): {r.text[:200]}")
            return r.json(), intento
        except LLMError:
            raise  # 4xx / modelo inexistente: reintentar no sirve
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError, httpx.HTTPStatusError) as exc:
            ultimo = exc
            if intento <= max_r:
                await asyncio.sleep(settings.ollama_reintento_espera_s * 2 ** (intento - 1))
    raise LLMNoDisponible(
        f"{settings.llm_provider} no responde en {settings.llm_base_url} tras {max_r + 1} intentos "
        f"({type(ultimo).__name__}). Comprueba que está arrancado y que el modelo "
        f"'{settings.llm_model}' está instalado.") from ultimo


async def chat(messages: list[dict], *, formato: dict | str | None = None,
               temperature: float | None = None, num_predict: int | None = None) -> ChatResultado:
    """Una petición de chat, serializada y con reintento acotado."""
    if settings.llm_provider == "ollama":
        est = estimar_tokens(messages)
        presupuesto = settings.ollama_num_ctx - (settings.ollama_num_predict if num_predict is None else num_predict)
        if est > presupuesto:
            raise ContextoExcedido(
                f"El prompt estimado ({est} tokens) no cabe en num_ctx={settings.ollama_num_ctx} "
                f"dejando {settings.ollama_num_ctx - presupuesto} para la respuesta. Reduce el historial o sube OLLAMA_NUM_CTX.")

    t0 = time.perf_counter()
    sem = _cola()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=settings.ollama_cola_timeout_s)
    except asyncio.TimeoutError as exc:
        raise LLMOcupado(
            f"El motor conversacional está ocupado (cola > {settings.ollama_cola_timeout_s:g} s). Reintenta en unos segundos.") from exc
    espera_ms = round((time.perf_counter() - t0) * 1000)
    try:
        async with _cliente(settings.ollama_timeout_s) as c:
            base = settings.llm_base_url.rstrip("/")
            if settings.llm_provider == "ollama":
                data, intentos = await _post_con_reintentos(
                    c, f"{base}/api/chat", _payload_ollama(messages, formato, temperature, num_predict))
                texto = (data.get("message") or {}).get("content", "")
                res = ChatResultado(
                    texto=texto, modelo=data.get("model", settings.llm_model),
                    prompt_tokens=data.get("prompt_eval_count"), eval_tokens=data.get("eval_count"),
                    ollama_ms=round(data["total_duration"] / 1e6) if data.get("total_duration") else None,
                    carga_ms=round(data["load_duration"] / 1e6) if data.get("load_duration") else None,
                    espera_cola_ms=espera_ms, intentos=intentos, ms_total=0)
                if res.prompt_tokens is not None and res.prompt_tokens >= settings.ollama_num_ctx:
                    raise ContextoExcedido(
                        f"Ollama evaluó {res.prompt_tokens} tokens de prompt con num_ctx={settings.ollama_num_ctx}: "
                        "el prompt se ha truncado. Sube OLLAMA_NUM_CTX o acorta el historial.")
            else:
                payload = _payload_openai(messages, formato, temperature, num_predict)
                data, intentos = await _post_con_reintentos(c, f"{base}/v1/chat/completions", payload)
                choices = data.get("choices") or []
                if not choices:
                    raise RespuestaInvalida("El proveedor no devolvió ninguna respuesta (sin 'choices').")
                u = data.get("usage") or {}
                res = ChatResultado(
                    texto=_sin_razonamiento((choices[0].get("message") or {}).get("content") or ""),
                    modelo=data.get("model", settings.llm_model),
                    prompt_tokens=u.get("prompt_tokens"), eval_tokens=u.get("completion_tokens"), ollama_ms=None,
                    carga_ms=None, espera_cola_ms=espera_ms, intentos=intentos, ms_total=0)
    finally:
        sem.release()
    res.ms_total = round((time.perf_counter() - t0) * 1000)
    return res


def extraer_json(texto: str) -> dict:
    """Primer objeto JSON del texto (tolera ```json ... ``` o texto alrededor)."""
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        raise RespuestaInvalida("El modelo no devolvió JSON.")
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise RespuestaInvalida(f"JSON inválido del modelo: {exc}") from exc
    if not isinstance(obj, dict):
        raise RespuestaInvalida("El JSON del modelo no es un objeto.")
    return obj


async def chat_completion(messages: list[dict], **kwargs) -> dict:
    """Compatibilidad con el código anterior: devuelve forma OpenAI {choices:[{message}]}."""
    r = await chat(messages, **kwargs)
    return {"model": r.modelo, "choices": [{"message": {"role": "assistant", "content": r.texto}}]}
