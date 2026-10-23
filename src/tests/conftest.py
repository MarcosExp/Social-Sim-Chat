import os
import uuid

import pytest

# Debe fijarse antes de importar app.*; TEST_DATABASE_URL tiene prioridad sobre DATABASE_URL.
if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from app import llm_client  # noqa: E402
from app.config import settings  # noqa: E402
from tests.fake_ollama import FakeOllama  # noqa: E402

PREFIJO = "TST-"


@pytest.fixture
def fake(monkeypatch):
    f = FakeOllama()
    monkeypatch.setattr(llm_client, "_TRANSPORT", f.transport())
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_model", "qwen3:14b")
    monkeypatch.setattr(settings, "ollama_host", "http://ollama.test:11434")
    monkeypatch.setattr(settings, "ollama_reintento_espera_s", 0.0)
    return f


def _bd_disponible():
    try:
        from sqlalchemy import text

        from app.db import engine
        with engine.connect() as c:
            return c.execute(text("SELECT to_regclass('conversacion_turno')")).scalar() is not None
    except Exception:
        return False


@pytest.fixture(scope="session")
def bd():
    if not _bd_disponible():
        pytest.skip("Postgres no disponible o sin migración 003 (define TEST_DATABASE_URL y aplica data/init-db/*.sql)")
    from app.db import engine
    return engine


@pytest.fixture
def alumno(bd):
    """Alumno de prueba (prefijo TST-) con competencia objetivo Metáfora; se borra al terminar."""
    from sqlalchemy import text
    sid = f"{PREFIJO}{uuid.uuid4().hex[:8]}"
    with bd.begin() as c:
        c.execute(text(
            "INSERT INTO student_profile_sim (student_id, competencia_objetivo, trayectoria_disenada, n_sesiones) "
            "VALUES (:s, 'Metáfora', 'progreso', 0)"), {"s": sid})
    yield sid
    with bd.begin() as c:
        c.execute(text("DELETE FROM student_profile_sim WHERE student_id = :s"), {"s": sid})


@pytest.fixture
def cliente(bd, fake):
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        yield c
