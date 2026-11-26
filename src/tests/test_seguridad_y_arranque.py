"""NF4: configuración segura al arrancar (clave del terapeuta) y precalentamiento del modelo."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app import llm_client
from app.config import settings
from app.llm_client import ESTADO_PRECALENTAMIENTO, describir_precalentamiento, precalentar_llm
from app.seguridad import CLAVE_DESARROLLO_CONOCIDA, ConfiguracionInsegura, comprobar_configuracion


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------------------------------------ clave del terapeuta
def test_una_clave_propia_no_genera_avisos_en_ningun_entorno():
    assert comprobar_configuracion("development", "k" * 32) == []
    assert comprobar_configuracion("production", "k" * 32) == []


@pytest.mark.parametrize("clave", [None, "", CLAVE_DESARROLLO_CONOCIDA])
def test_en_desarrollo_la_clave_vacia_o_publica_solo_avisa(clave):
    avisos = comprobar_configuracion("development", clave)
    assert len(avisos) == 1 and "make up" in avisos[0]


@pytest.mark.parametrize("entorno", ["production", "staging", ""])
@pytest.mark.parametrize("clave", [None, "", CLAVE_DESARROLLO_CONOCIDA])
def test_fuera_de_desarrollo_la_clave_vacia_o_publica_impide_arrancar(entorno, clave):
    with pytest.raises(ConfiguracionInsegura) as e:
        comprobar_configuracion(entorno, clave)
    assert "environment/.env" in str(e.value)


def test_el_backend_no_arranca_en_produccion_con_la_clave_de_desarrollo(monkeypatch, fake):
    from app.main import app
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "api_key_terapeuta", CLAVE_DESARROLLO_CONOCIDA)
    with pytest.raises(ConfiguracionInsegura):
        with TestClient(app):
            pass


def test_el_backend_arranca_en_produccion_con_clave_propia(monkeypatch, fake):
    from app.main import app
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "api_key_terapeuta", "una-clave-larga-y-propia-1234")
    with TestClient(app) as c:
        assert c.get("/").status_code == 200


def test_el_compose_ya_no_trae_la_clave_publica_por_defecto():
    """La clave de desarrollo no puede volver a colarse como valor por defecto del compose ni de .env.example."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[2]
    ficheros = ("environment/docker-compose.yml", "environment/.env.example")
    if not all((raiz / f).exists() for f in ficheros):      # `make test` corre en el contenedor, donde solo está src/
        pytest.skip("solo en el repositorio completo (environment/ no está en el contenedor del backend)")
    for f in ficheros:
        for linea in (raiz / f).read_text(encoding="utf-8").splitlines():
            if "API_KEY_TERAPEUTA" in linea and not linea.lstrip().startswith("#"):
                assert CLAVE_DESARROLLO_CONOCIDA not in linea, f"{f}: {linea}"


# ------------------------------------------------------------------------------------------------ precalentamiento
@pytest.fixture
def activo(monkeypatch):
    monkeypatch.setattr(settings, "llm_precalentar", True)
    yield
    ESTADO_PRECALENTAMIENTO.update(estado="no_aplica", ms=None, detalle="")


def test_precalentar_envia_un_turno_minimo_con_la_misma_configuracion_del_chat(fake, activo):
    r = run(precalentar_llm())
    assert r["estado"] == "ok" and r["ms"] is not None
    p = fake.peticiones[0]
    assert fake.llamadas_chat == 1
    assert p["options"]["num_predict"] == 1                       # coste mínimo
    assert p["options"]["num_ctx"] == settings.ollama_num_ctx     # el mismo num_ctx: si cambia, Ollama recarga el modelo
    assert p["think"] is False and p["keep_alive"] == settings.ollama_keep_alive
    assert describir_precalentamiento().startswith("ok (")


def test_precalentar_no_hace_nada_en_modo_simulado_ni_si_esta_desactivado(fake, monkeypatch):
    monkeypatch.setattr(settings, "llm_precalentar", False)
    assert run(precalentar_llm())["estado"] == "no_aplica" and fake.llamadas_chat == 0
    monkeypatch.setattr(settings, "llm_precalentar", True)
    monkeypatch.setattr(settings, "llm_provider", "simulado")
    assert run(precalentar_llm())["estado"] == "no_aplica" and fake.llamadas_chat == 0
    ESTADO_PRECALENTAMIENTO.update(estado="no_aplica", ms=None, detalle="")


def test_precalentar_nunca_lanza_y_cuenta_el_error_si_el_modelo_no_existe(fake, activo):
    fake.fallos = [404]
    r = run(precalentar_llm())
    assert r["estado"] == "error" and "no está en el proveedor" in r["detalle"]
    assert fake.llamadas_chat == 1                                # un modelo inexistente no se reintenta
    assert describir_precalentamiento().startswith("error:")


def test_precalentar_espera_a_que_el_motor_termine_de_arrancar(fake, activo, monkeypatch):
    monkeypatch.setattr(settings, "ollama_max_reintentos", 0)
    fake.fallos = ["connect", "connect"]
    r = run(precalentar_llm(intentos=4, espera_s=0.0))
    assert r["estado"] == "ok" and fake.llamadas_chat == 3


def test_precalentar_se_rinde_tras_los_intentos_y_no_tumba_el_backend(fake, activo, monkeypatch):
    monkeypatch.setattr(settings, "ollama_max_reintentos", 0)
    fake.caido = True
    r = run(precalentar_llm(intentos=2, espera_s=0.0))
    assert r["estado"] == "error" and "no responde" in r["detalle"]


def test_el_arranque_lanza_el_precalentamiento_en_segundo_plano(fake, activo, monkeypatch):
    from app.main import app
    with TestClient(app) as c:
        for _ in range(50):                      # la tarea corre en el bucle del TestClient: se espera a que termine
            if fake.llamadas_chat:
                break
            import time
            time.sleep(0.05)
        assert fake.llamadas_chat == 1
        assert c.get("/").status_code == 200


def test_health_informa_del_precalentamiento(cliente):
    h = cliente.get("/health").json()
    assert "llm_precalentamiento" in h
