"""ADR-003: el dashboard solo habla con la API. Estas pruebas fallan si vuelve a abrir Postgres o a leer ficheros del modelo,
y comprueban de extremo a extremo la consola del terapeuta (dashboard -> API -> recálculo de métricas)."""
import re
from pathlib import Path

import pytest

from tests.test_er_v2 import _terminar_con

DASH = Path(__file__).resolve().parent.parent / "dashboard"


def test_el_dashboard_no_accede_a_la_base_de_datos():
    prohibido = re.compile(r"sqlalchemy|psycopg|DATABASE_URL|create_engine|read_sql|METRICS_PATH|\.joblib|metrics\.json", re.I)
    for f in DASH.glob("*.py"):
        malos = [l.strip() for l in f.read_text(encoding="utf-8").splitlines()
                 if prohibido.search(l) and not l.lstrip().startswith("#")]
        assert not malos, f"{f.name} no debe acceder a datos fuera de la API: {malos}"
    assert "sqlalchemy" not in (DASH / "requirements.txt").read_text().lower()
    compose = (DASH.parent.parent / "environment" / "docker-compose.yml").read_text(encoding="utf-8")
    bloque = compose[compose.index("  dashboard:"):compose.index("volumes:\n  pgdata:")]
    assert "DATABASE_URL" not in bloque and "BACKEND_URL" in bloque


@pytest.fixture
def dashboard(cliente, monkeypatch):
    """AppTest del dashboard con su cliente HTTP apuntando a la API de pruebas (TestClient, sin red)."""
    st = pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    monkeypatch.syspath_prepend(str(DASH))
    import cliente_api
    monkeypatch.setattr(cliente_api, "_cliente", cliente)
    st.cache_data.clear()
    yield lambda: AppTest.from_file(str(DASH / "app.py"), default_timeout=60).run()
    st.cache_data.clear()


def _sin_fallos(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_dashboard_arranca_solo_con_la_api(dashboard, cliente, alumno, fake):
    _terminar_con(cliente, fake, alumno, ())
    at = dashboard()
    _sin_fallos(at)
    assert [t.label for t in at.tabs] == ["Pipeline", "Alumno", "Modelo", "Conversación", "Sesiones reales", "Consola del terapeuta"]


def test_consola_corrige_un_turno_y_recalcula(dashboard, cliente, alumno, fake):
    cid = _terminar_con(cliente, fake, alumno, (0,) * 10)               # todo 0: PEPE = 0
    antes = cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()[0]
    assert antes["PEPE"] == 0.0
    at = dashboard()
    _sin_fallos(at)
    at.text_input(key="consola_autor").set_value("Álvaro Núñez").run()
    at.selectbox(key="consola_sesion").select(antes["session_id"]).run()
    at.radio(key="consola_valor").set_value("2 · correcta").run()
    [b for b in at.button if b.label == "Guardar corrección del turno"][0].click().run()
    _sin_fallos(at)
    assert any("Turno" in s.value and "corregido" in s.value for s in at.success), [s.value for s in at.success]
    despues = cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()[0]
    assert despues["PEPE"] > 0.0
    corregidos = [t for t in cliente.get(f"/conversaciones/{cid}").json()["turnos"] if t["accuracy_corregido"] == 2]
    assert len(corregidos) == 1 and corregidos[0]["evaluacion"] == 0         # el original se conserva
    assert [r["autor"] for r in cliente.get("/correcciones", params={"conversacion_id": cid}).json()] == ["Álvaro Núñez"]


def test_consola_guarda_etiqueta_y_nota(dashboard, cliente, alumno, fake):
    _terminar_con(cliente, fake, alumno, ())
    sesion = cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()[0]
    at = dashboard()
    at.text_input(key="consola_autor").set_value("Álvaro Núñez").run()
    at.selectbox(key="consola_sesion").select(sesion["session_id"]).run()
    at.selectbox(key=f"consola_etq_{sesion['session_id']}").select("Estancamiento").run()
    at.text_area(key=f"consola_nota_{sesion['session_id']}").set_value("se frustra con las metáforas").run()
    [b for b in at.button if b.label == "Guardar etiqueta y nota"][0].click().run()
    _sin_fallos(at)
    d = cliente.get(f"/sessions/{sesion['session_id']}").json()
    assert d["etiqueta_corregida"] == "estancamiento" and d["nota_clinica"] == "se frustra con las metáforas"
    assert {r["autor"] for r in cliente.get("/correcciones", params={"session_id": sesion["session_id"]}).json()} == {"Álvaro Núñez"}


def test_el_dashboard_avisa_si_la_api_no_responde(monkeypatch):
    st = pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    import httpx
    monkeypatch.syspath_prepend(str(DASH))
    import cliente_api
    monkeypatch.setattr(cliente_api, "_cliente", httpx.Client(base_url="http://127.0.0.1:9", timeout=1))
    st.cache_data.clear()
    at = AppTest.from_file(str(DASH / "app.py"), default_timeout=60).run()
    assert not at.exception and any("No se puede llegar a la API" in e.value for e in at.error)


def test_las_horas_se_muestran_en_hora_peninsular(dashboard, cliente, alumno, fake):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    _terminar_con(cliente, fake, alumno, (0,) * 10)
    sesion = cliente.get("/sessions", params={"student_id": alumno, "origen": "real"}).json()[0]
    at = dashboard()
    at.text_input(key="consola_autor").set_value("Álvaro Núñez").run()
    at.selectbox(key="consola_sesion").select(sesion["session_id"]).run()
    at.radio(key="consola_valor").set_value("2 · correcta").run()
    [b for b in at.button if b.label == "Guardar corrección del turno"][0].click().run()
    _sin_fallos(at)
    # en la tabla del historial, la hora es la peninsular de la fecha UTC que guarda la API
    log = cliente.get("/correcciones", params={"conversacion_id": sesion["conversacion_id"]}).json()
    utc = datetime.fromisoformat(log[0]["fecha"].replace("Z", "+00:00"))
    esperado = utc.astimezone(ZoneInfo("Europe/Madrid")).strftime("%d/%m/%Y %H:%M:%S")
    tablas = [d.value for d in at.dataframe if "fecha (hora peninsular)" in d.value.columns]
    assert tablas and esperado in set(tablas[-1]["fecha (hora peninsular)"])
    assert any("hora peninsular" in c.value for c in at.caption)
