"""Proveedor «openai» (API compatible con OpenAI) contra un servidor simulado.

NF2 fija que el backend accede al LLM mediante una interfaz compatible con OpenAI para poder sustituir el motor local
sin cambiar el resto del sistema. Estos tests comprueban el contrato del cliente y que una conversación completa
funciona igual con el proveedor «openai» que con la API nativa de Ollama. No sustituyen una prueba con un servidor real
(`LLM_PROVIDER=openai make smoke`).
"""
import asyncio

import pytest

from app import llm_client
from app.config import settings
from app.conversacion import SCHEMA_EVALUACION
from app.llm_client import LLMError, LLMNoDisponible, ModeloNoEncontrado, RespuestaInvalida, chat, diagnostico_llm
from tests.test_api_conversacion import hasta_primera_figura, turno

MSG = [{"role": "system", "content": "hola"}, {"role": "user", "content": "buenas"}]


def run(coro):
    return asyncio.run(coro)


def test_payload_compatible_con_openai_sin_claves_de_ollama(fake_openai):
    res = run(chat(MSG, formato=SCHEMA_EVALUACION, temperature=0.1, num_predict=50))
    p = fake_openai.peticiones[0]
    assert p["model"] == "qwen3:14b" and p["messages"] == MSG
    assert p["stream"] is False and p["temperature"] == 0.1 and p["max_tokens"] == 50
    assert not {"think", "options", "keep_alive", "format"} & set(p)        # claves de la API nativa
    assert res.prompt_tokens == 120 and res.eval_tokens == 25
    assert res.carga_ms is None and res.ollama_ms is None and res.intentos == 1


def test_max_tokens_por_defecto_es_el_tope_de_turno(fake_openai):
    run(chat(MSG))
    assert fake_openai.peticiones[0]["max_tokens"] == settings.ollama_num_predict


def test_response_format_json_schema_sin_mutar_el_schema_del_evaluador(fake_openai):
    antes = dict(SCHEMA_EVALUACION)
    run(chat(MSG, formato=SCHEMA_EVALUACION))
    rf = fake_openai.peticiones[0]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"]["properties"] == SCHEMA_EVALUACION["properties"]
    assert rf["json_schema"]["schema"]["additionalProperties"] is False
    assert SCHEMA_EVALUACION == antes and "additionalProperties" not in SCHEMA_EVALUACION   # la huella del evaluador no cambia


def test_response_format_se_puede_desactivar_y_no_se_envia_sin_formato(fake_openai, monkeypatch):
    run(chat(MSG))
    monkeypatch.setattr(settings, "llm_compat_response_format", False)
    run(chat(MSG, formato=SCHEMA_EVALUACION))
    assert all("response_format" not in p for p in fake_openai.peticiones)


def test_clave_de_api_va_como_bearer_y_sin_clave_no_hay_cabecera(fake_openai, monkeypatch):
    run(chat(MSG))
    assert "authorization" not in fake_openai.cabeceras[0]
    monkeypatch.setattr(settings, "llm_compat_api_key", "secreto-local")
    run(chat(MSG))
    assert fake_openai.cabeceras[1]["authorization"] == "Bearer secreto-local"


def test_se_retiran_los_bloques_think(fake_openai):
    fake_openai.respuestas = ['<think>\nrazono un poco\n</think>\n{"evaluacion": 1}']
    assert run(chat(MSG)).texto == '{"evaluacion": 1}'


def test_respuesta_sin_choices_es_respuesta_invalida(fake_openai, monkeypatch):
    import httpx

    monkeypatch.setattr(llm_client, "_TRANSPORT", httpx.MockTransport(lambda req: httpx.Response(200, json={"model": "x", "choices": []})))
    with pytest.raises(RespuestaInvalida):
        run(chat(MSG))


def test_reintenta_5xx_y_no_reintenta_4xx(fake_openai, monkeypatch):
    monkeypatch.setattr(settings, "ollama_max_reintentos", 2)
    fake_openai.fallos = ["connect", 503]
    assert run(chat(MSG)).intentos == 3
    fake_openai.fallos, fake_openai.llamadas_chat = [400], 0
    with pytest.raises(LLMError):
        run(chat(MSG))
    assert fake_openai.llamadas_chat == 1


def test_agota_reintentos_con_mensaje_que_nombra_el_proveedor(fake_openai, monkeypatch):
    monkeypatch.setattr(settings, "ollama_max_reintentos", 1)
    fake_openai.fallos = ["timeout"] * 5
    with pytest.raises(LLMNoDisponible) as e:
        run(chat(MSG))
    assert "openai" in e.value.mensaje and "http://compat.test:11434" in e.value.mensaje


def test_modelo_inexistente_no_sugiere_ollama_pull(fake_openai):
    fake_openai.fallos = [404]
    with pytest.raises(ModeloNoEncontrado) as e:
        run(chat(MSG))
    assert "ollama pull" not in e.value.mensaje


def test_diagnostico_ok_modelo_ausente_y_servidor_caido(fake_openai):
    d = run(diagnostico_llm())
    assert d["estado"] == "ok" and d["modelo_disponible"] is True
    fake_openai.modelos = ["otro-modelo"]
    d = run(diagnostico_llm())
    assert d["estado"] == "error" and d["modelo_disponible"] is False and "LLM_COMPAT_MODEL" in d["detalle"]
    fake_openai.caido = True
    d = run(diagnostico_llm())
    assert d["estado"] == "error" and "no se puede conectar" in d["detalle"]


def test_alias_tabbyapi_conserva_su_comportamiento(fake_openai, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "tabbyapi")
    monkeypatch.setattr(settings, "tabbyapi_host", "http://tabby.test:5000")
    monkeypatch.setattr(settings, "tabbyapi_model", "qwen3:14b")
    monkeypatch.setattr(settings, "tabbyapi_api_key", "k")
    assert settings.llm_openai_compatible and settings.llm_base_url == "http://tabby.test:5000"
    run(chat(MSG, formato=SCHEMA_EVALUACION))
    assert fake_openai.cabeceras[0]["x-api-key"] == "k" and "authorization" not in fake_openai.cabeceras[0]
    assert "response_format" not in fake_openai.peticiones[0] and fake_openai.peticiones[0]["max_tokens"]


# --- el resto del sistema no cambia al sustituir el motor ---------------------------------------------------------
@pytest.fixture
def cliente_openai(bd, fake_openai):
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        yield c


def test_conversacion_completa_con_el_proveedor_openai(cliente_openai, alumno, fake_openai):
    cid, _ = hasta_primera_figura(cliente_openai, alumno)
    assert fake_openai.llamadas_chat == 0
    for _ in range(4):
        fake_openai.respuestas = [2]
        r = turno(cliente_openai, cid, "respuesta correcta", latencia_ms=1200).json()
        assert r["evaluacion"] == 2 and r["evaluacion_origen"] == "llm"
        assert r["llm"]["modelo"] == "qwen3:14b" and r["llm"]["intentos"] == 1
    assert r["estado"] == "terminada" and fake_openai.llamadas_chat == 4
    assert all(p["response_format"]["type"] == "json_schema" for p in fake_openai.peticiones)
    assert cliente_openai.get(f"/conversaciones/{cid}").json()["modelo"] == "qwen3:14b"


def test_llm_caido_da_503_reintentable_tambien_con_openai(cliente_openai, alumno, fake_openai):
    cid, _ = hasta_primera_figura(cliente_openai, alumno)
    fake_openai.caido = True
    r = turno(cliente_openai, cid, "respuesta")
    assert r.status_code == 503 and r.json()["codigo"] == "llm_no_disponible" and r.json()["reintentable"] is True


def test_health_informa_del_proveedor_y_del_modelo(cliente_openai, fake_openai):
    h = cliente_openai.get("/health").json()
    assert h["llm_provider"] == "openai" and h["llm"] == "ok" and h["llm_modelo_disponible"] is True
    fake_openai.modelos = []
    h = cliente_openai.get("/health").json()
    assert h["status"] == "degraded" and "LLM_COMPAT_MODEL" in h["llm"]


def test_pide_reasoning_effort_none_por_defecto_y_se_puede_quitar(fake_openai, monkeypatch):
    """Con el /v1 de Ollama y qwen3 el razonamiento se come max_tokens (medido en real): por defecto se desactiva."""
    run(chat(MSG))
    monkeypatch.setattr(settings, "llm_compat_reasoning_effort", None)
    run(chat(MSG))
    assert fake_openai.peticiones[0]["reasoning_effort"] == "none"
    assert "reasoning_effort" not in fake_openai.peticiones[1]


def test_respuesta_cortada_por_longitud_explica_como_arreglarlo(fake_openai, monkeypatch):
    import httpx

    cortada = {"model": "x", "choices": [{"index": 0, "finish_reason": "length",
                                          "message": {"role": "assistant", "content": '{\n\n"analis'}}]}
    monkeypatch.setattr(llm_client, "_TRANSPORT", httpx.MockTransport(lambda req: httpx.Response(200, json=cortada)))
    with pytest.raises(RespuestaInvalida, match="LLM_COMPAT_REASONING_EFFORT"):
        run(chat(MSG, formato=SCHEMA_EVALUACION))
    assert run(chat(MSG)).texto == '{\n\n"analis'          # sin formato JSON exigido, un texto largo cortado sigue siendo utilizable
