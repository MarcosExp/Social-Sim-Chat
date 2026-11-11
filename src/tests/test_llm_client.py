"""Contrato del cliente de Ollama contra un servidor simulado (sin red, sin Postgres)."""
import asyncio

import pytest

from app import llm_client
from app.config import settings
from app.llm_client import (ContextoExcedido, LLMNoDisponible, ModeloNoEncontrado, RespuestaInvalida, chat,
                            diagnostico_llm, extraer_json)

MSG = [{"role": "system", "content": "hola"}, {"role": "user", "content": "buenas"}]


def run(coro):
    return asyncio.run(coro)


def test_payload_num_ctx_think_keep_alive(fake):
    res = run(chat(MSG, formato={"type": "object"}))
    p = fake.peticiones[0]
    assert p["model"] == "qwen3:14b"
    assert p["stream"] is False
    assert p["think"] is False
    assert p["keep_alive"] == settings.ollama_keep_alive and settings.ollama_keep_alive
    assert p["options"]["num_ctx"] == settings.ollama_num_ctx == 8192
    assert p["options"]["num_predict"] == settings.ollama_num_predict
    assert p["format"] == {"type": "object"}
    assert res.intentos == 1 and res.carga_ms == 5 and res.prompt_tokens == 120


def test_sin_format_no_se_envia(fake):
    run(chat(MSG))
    assert "format" not in fake.peticiones[0]


def test_reintenta_conexion_y_5xx_con_limite(fake, monkeypatch):
    monkeypatch.setattr(settings, "ollama_max_reintentos", 2)
    fake.fallos = ["connect", 503]
    res = run(chat(MSG))
    assert res.intentos == 3 and fake.llamadas_chat == 3


def test_agota_reintentos_y_da_mensaje_claro(fake, monkeypatch):
    monkeypatch.setattr(settings, "ollama_max_reintentos", 2)
    fake.fallos = ["timeout"] * 10
    with pytest.raises(LLMNoDisponible) as e:
        run(chat(MSG))
    assert fake.llamadas_chat == 3  # 1 + 2 reintentos, ni uno más
    assert "3 intentos" in e.value.mensaje and "ollama" in e.value.mensaje.lower()
    assert e.value.reintentable


def test_4xx_no_se_reintenta(fake):
    fake.fallos = [400]
    with pytest.raises(llm_client.LLMError):
        run(chat(MSG))
    assert fake.llamadas_chat == 1


def test_modelo_inexistente_no_se_reintenta(fake):
    fake.fallos = [404]
    with pytest.raises(ModeloNoEncontrado) as e:
        run(chat(MSG))
    assert fake.llamadas_chat == 1 and "ollama pull qwen3:14b" in e.value.mensaje


def test_contexto_excedido_antes_de_enviar(fake):
    grande = [{"role": "user", "content": "x" * (settings.ollama_num_ctx * 4)}]
    with pytest.raises(ContextoExcedido):
        run(chat(grande))
    assert fake.llamadas_chat == 0


def test_contexto_excedido_si_ollama_trunca(fake):
    fake.prompt_eval_count = settings.ollama_num_ctx
    with pytest.raises(ContextoExcedido):
        run(chat(MSG))


def test_peticiones_concurrentes_se_serializan(fake):
    fake.retardo_s = 0.05

    async def varias():
        return await asyncio.gather(*[chat(MSG) for _ in range(5)])

    res = run(varias())
    assert fake.max_en_vuelo == 1
    assert max(r.espera_cola_ms for r in res) >= 100  # las últimas esperaron a las anteriores


def test_cola_saturada_da_llm_ocupado(fake, monkeypatch):
    monkeypatch.setattr(settings, "ollama_cola_timeout_s", 0.05)
    fake.retardo_s = 0.3

    async def dos():
        return await asyncio.gather(chat(MSG), chat(MSG), return_exceptions=True)

    a, b = run(dos())
    assert isinstance(b, llm_client.LLMOcupado) or isinstance(a, llm_client.LLMOcupado)


def test_diagnostico_ok(fake):
    d = run(diagnostico_llm())
    assert d["estado"] == "ok" and d["modelo_disponible"] is True


def test_diagnostico_modelo_ausente(fake):
    fake.modelos = ["llama3:8b"]
    d = run(diagnostico_llm())
    assert d["estado"] == "error" and d["modelo_disponible"] is False
    assert "ollama pull qwen3:14b" in d["detalle"]


def test_diagnostico_ollama_caido(fake):
    fake.caido = True
    d = run(diagnostico_llm())
    assert d["estado"] == "error" and "OLLAMA_HOST=0.0.0.0" in d["detalle"]


def test_extraer_json_tolerante():
    assert extraer_json('Claro:\n```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(RespuestaInvalida):
        extraer_json("sin json")
    with pytest.raises(RespuestaInvalida):
        extraer_json("{roto")
