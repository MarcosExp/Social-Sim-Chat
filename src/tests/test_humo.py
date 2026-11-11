"""Prueba de humo REAL (Ollama + backend levantados). No corre por defecto:

    python -m pytest -m humo -s           # BACKEND_URL por defecto http://localhost:8010
"""
import pytest

pytestmark = pytest.mark.humo


def test_conversacion_completa_con_ollama_real():
    from scripts import smoke_conversacion
    import sys
    sys.argv = ["smoke"]
    assert smoke_conversacion.main() == 0
