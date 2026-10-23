"""Métricas por sesión: función pura + registro automático al terminar la conversación."""
from types import SimpleNamespace as T

import pytest

from app import metricas
from tests.test_api_conversacion import crear, hasta_primera_figura, turno


def t(rol, tipo, texto, evaluacion=None, intento=1, rama=None, latencia_ms=None, nodo=None):
    return T(rol=rol, tipo=tipo, texto=texto, evaluacion=evaluacion, intento=intento, rama=rama, latencia_ms=latencia_ms,
             nodo=nodo)


def test_calcular_a_mano():
    turnos = [
        t("bot", "apertura", "hola"),
        t("menor", "apertura", "hola", rama="responde", latencia_ms=500),
        t("menor", "apertura", "hoy he jugado mucho", rama="comparte"),          # iniciativa
        t("menor", "competencia", "esta nervioso", evaluacion=2, latencia_ms=2000, nodo="M1"),               # 2 palabras
        t("menor", "competencia", "¿qué es eso?", evaluacion=0, latencia_ms=4000, nodo="M2"),                # 3 palabras, pregunta
        t("menor", "competencia", "que se ha ido lejos", evaluacion=1, intento=2, latencia_ms=3000, nodo="M2"),  # 2º intento
    ]
    m = metricas.calcular(turnos)
    assert m.aMLU == pytest.approx((2 + 5) / 2, abs=0.01)                 # competencia con valoración >= 1 (se excluye el 0)
    assert m.n_turnos_amlu == 2
    assert m.latencia_pragmatica_ms == 2500                              # LPP global, apertura incluida: mediana de 500, 2000, 4000, 3000
    assert (m.lpp_intento1, m.lpp_intento2) == (3000, 3000)               # solo competencia: [2000, 4000] y [3000]
    assert m.IRC_pct == 40.0                                             # 2 de 5 turnos del menor
    assert m.PEPE == 1.0                                                 # por figura: M1 = 2; M2 (0 y luego 1, sin acertar) = 0
    assert m.pct_DET == m.pct_DET_observado_en_turnos == pytest.approx(33.3, abs=0.1)
    assert (m.n_turnos_menor, m.n_turnos_evaluados) == (5, 3)


def test_calcular_sin_datos_no_revienta():
    m = metricas.calcular([t("bot", "apertura", "hola")])
    assert m.aMLU is None and m.n_turnos_amlu == 0                      # sin turnos válidos: aMLU nulo («sin datos»), no 0
    assert m.PEPE is None and m.IRC_pct is None and m.latencia_pragmatica_ms is None


def test_sesion_real_se_registra_al_terminar(cliente, alumno, fake, bd):
    from sqlalchemy import text
    cid, _ = hasta_primera_figura(cliente, alumno)

    def fila():
        with bd.connect() as c:
            return c.execute(text("SELECT * FROM session_data WHERE conversacion_id = :c"), {"c": cid}).mappings().first()

    fake.respuestas = [2]
    turno(cliente, cid, "es una forma de hablar", latencia_ms=2500)
    assert fila() is None                                                # en curso: todavía no hay sesión
    for ev in (0, 2, 2, 2):                                                 # M2: 0 → ayuda → 2; M3, M4 ok
        fake.respuestas = [ev]
        r = turno(cliente, cid, "respuesta de prueba larga", latencia_ms=3500).json()
    assert r["estado"] == "terminada"
    f = fila()
    assert f["sesion_num"] == 1 and f["competencia"] == "Metáfora"
    assert f["n_turnos_evaluados"] == 5 and f["definicion_version"] == metricas.DEFINICION_VERSION
    assert float(f["pepe"]) == pytest.approx((2 + 1 + 2 + 2) / 4, abs=0.01)   # M2 acierta con la ayuda = 1
    assert f["latencia_pragmatica_ms"] == 3500
    assert (f["lpp_intento1"], f["lpp_intento2"]) == (3500, 3500)         # competencia: intento 1 [2500, 3500, 3500, 3500]; intento 2 [3500]
    # segunda conversación del mismo alumno → sesion_num 2
    c2 = crear(cliente, alumno)["conversacion_id"]
    turno(cliente, c2, "hola"); turno(cliente, c2, "sí")
    for _ in range(4):
        fake.respuestas = [2]
        turno(cliente, c2, "bien")
    with bd.connect() as c:
        assert c.execute(text("SELECT sesion_num FROM session_data WHERE conversacion_id = :c"), {"c": c2}).scalar() == 2


def test_fallo_al_registrar_no_rompe_la_conversacion(cliente, alumno, fake, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("tabla inexistente")
    monkeypatch.setattr(metricas, "registrar_sesion", boom)
    cid, _ = hasta_primera_figura(cliente, alumno)
    for _ in range(4):
        fake.respuestas = [2]
        r = turno(cliente, cid, "bien")
    assert r.status_code == 200 and r.json()["estado"] == "terminada"


def test_conversacion_de_prueba_no_genera_sesion_real(cliente, alumno, fake, bd):
    from sqlalchemy import text
    cid = crear(cliente, alumno, prueba=True)["conversacion_id"]
    turno(cliente, cid, "hola"); turno(cliente, cid, "sí")
    for _ in range(4):
        fake.respuestas = [2]
        r = turno(cliente, cid, "bien").json()
    assert r["estado"] == "terminada"
    with bd.connect() as c:
        assert c.execute(text("SELECT count(*) FROM session_data WHERE origen = 'real' AND student_id = :s"), {"s": alumno}).scalar() == 0
    assert cliente.get(f"/conversaciones/{cid}").json()["es_prueba"] is True


def test_recalculo_es_idempotente(cliente, alumno, fake, bd):
    from sqlalchemy import text

    from scripts import metricas_reales
    cid = crear(cliente, alumno)["conversacion_id"]
    turno(cliente, cid, "hola"); turno(cliente, cid, "sí")
    for _ in range(4):
        fake.respuestas = [2]
        turno(cliente, cid, "bien")
    with bd.begin() as c:
        c.execute(text("DELETE FROM session_data WHERE conversacion_id = :c"), {"c": cid})
    metricas_reales.sincronizar(recalcular=False)
    metricas_reales.sincronizar(recalcular=True)
    with bd.connect() as c:
        assert c.execute(text("SELECT count(*) FROM session_data WHERE conversacion_id = :c"), {"c": cid}).scalar() == 1


def test_fuera_de_rango_distingue_minmax_de_p5_p95():
    import pandas as pd
    from scripts.metricas_reales import fuera_de_rango
    corpus = pd.Series(range(0, 101))                    # mín 0, máx 100, p5 = 5, p95 = 95
    real = pd.Series([-1, 2, 50, 98, 101])               # fuera de mín-máx: -1 y 101; fuera de p5-p95: -1, 2, 98 y 101
    assert fuera_de_rango(real, corpus) == (40.0, 80.0)


def test_session_data_tiene_las_columnas_del_desglose_de_sesiones_reales(bd):
    from sqlalchemy import text
    from app.models import SessionData
    nuevas = {"n_figuras", "n_turnos_amlu", "lpp_intento1", "lpp_intento2"}
    with bd.connect() as c:
        en_bd = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'session_data'"))}
    assert nuevas <= en_bd and all(hasattr(SessionData, n) for n in nuevas)
    assert {"n_figuras", "n_turnos_amlu", "lpp_intento1", "lpp_intento2"} <= set(metricas.Metricas.__dataclass_fields__)


def test_pepe_se_puntua_por_figura_no_por_intento():
    """2 = acierta sin ayuda; 1 = falla o es parcial y acierta tras la ayuda; 0 = no acierta (decisión de Álvaro, 2026-10-12)."""
    turnos = [
        t("menor", "competencia", "bien", evaluacion=2, nodo="M1"),                    # figura 1: 2
        t("menor", "competencia", "no sé", evaluacion=0, nodo="M2"),
        t("menor", "competencia", "ya lo veo", evaluacion=2, intento=2, nodo="M2"),    # figura 2: 0 y luego 2 -> 1
        t("menor", "competencia", "mmm", evaluacion=0, nodo="M3"),
        t("menor", "competencia", "ah vale", evaluacion=2, intento=2, nodo="M3"),      # figura 3: 1
        t("menor", "competencia", "algo", evaluacion=1, nodo="M4"),
        t("menor", "competencia", "algo más", evaluacion=1, intento=2, nodo="M4"),     # figura 4: parcial y sin acertar -> 0
    ]
    m = metricas.calcular(turnos)
    assert m.PEPE == pytest.approx((2 + 1 + 1 + 0) / 4)      # antes (1.er intento): (2 + 0 + 0 + 1) / 4 = 0,75
    assert metricas.puntuar_figuras(turnos) == {"M1": 2, "M2": 1, "M3": 1, "M4": 0}


def test_pct_det_es_provisional_y_no_es_entrada_del_clasificador_sobre_reales():
    """Decisión de Álvaro, 2026-10-12: %DET se mantiene pero marcado provisional y fuera del clasificador sobre sesiones reales."""
    from scripts.metricas_reales import etiqueta
    assert "pct_DET" in metricas.PROVISIONALES
    assert metricas.columnas_para_clasificador() == ("aMLU", "latencia_pragmatica_ms", "IRC_pct", "PEPE")
    assert etiqueta("pct_DET") == "pct_DET (provisional)" and etiqueta("latencia_pragmatica_ms") == "latencia_pragmatica_ms"


def test_amlu_solo_cuenta_turnos_de_competencia_con_valoracion_al_menos_1():
    """Decisión de Álvaro, 2026-10-12: los turnos con 0 (literal, vacío, sin sentido) no cuentan; sin ninguno, aMLU nulo (v3)."""
    turnos = [
        t("menor", "apertura", "hoy he jugado en el parque con mi hermano", rama="comparte"),   # apertura: no cuenta
        t("menor", "competencia", "uno dos tres cuatro cinco", evaluacion=0, nodo="M1"),         # 0: no cuenta
        t("menor", "competencia", "cuatro cinco", evaluacion=1, nodo="M1", intento=2),           # 2 palabras
        t("menor", "competencia", "seis siete ocho nueve", evaluacion=2, nodo="M2"),             # 4 palabras
    ]
    m = metricas.calcular(turnos)
    assert m.aMLU == 3.0 and m.n_turnos_amlu == 2
    sin_validos = [t("menor", "competencia", "asdkj qwpo zzz", evaluacion=0, nodo="M1")]
    m0 = metricas.calcular(sin_validos)
    assert m0.aMLU is None and m0.n_turnos_amlu == 0       # v3: «sin datos» no es «cero palabras»


def test_lpp_es_global_con_apertura_y_se_desglosa_por_intento():
    """Decisión de Álvaro, 2026-10-12: LPP = mediana de TODOS los turnos del menor (apertura incluida);
    además `lpp_intento1` y `lpp_intento2` (solo competencia) por separado."""
    turnos = [
        t("menor", "apertura", "hola", rama="responde", latencia_ms=500),
        t("menor", "apertura", "sí", rama="afirmativa", latencia_ms=1500),
        t("menor", "competencia", "a", evaluacion=0, nodo="M1", intento=1, latencia_ms=2000),
        t("menor", "competencia", "b", evaluacion=2, nodo="M1", intento=2, latencia_ms=3000),
        t("menor", "competencia", "c", evaluacion=0, nodo="M2", intento=1, latencia_ms=4000),
        t("menor", "competencia", "d", evaluacion=2, nodo="M2", intento=2, latencia_ms=5000),
    ]
    m = metricas.calcular(turnos)
    assert m.latencia_pragmatica_ms == 2500          # mediana de 500, 1500, 2000, 3000, 4000, 5000 (antes: 3500, solo competencia)
    assert m.lpp_intento1 == 3000 and m.lpp_intento2 == 4000
    sin = metricas.calcular([t("menor", "competencia", "a", evaluacion=0, nodo="M1", latencia_ms=2000)])
    assert sin.lpp_intento2 is None                   # no hubo segundo intento


def test_irc_en_preguntas_reciprocas_cuenta_compartir_algo_propio():
    """Decisión de Álvaro, 2026-10-12: en «Preguntas recíprocas» una respuesta valorada 2 (compartir algo propio, aunque
    no lleve «?») cuenta como iniciativa, además de los «?»/«¿» y de la rama `comparte` de la apertura."""
    turnos = [
        t("menor", "apertura", "hola", rama="responde"),
        t("menor", "competencia", "Yo he jugado con mi hermano", evaluacion=2, nodo="P1"),   # comparte: iniciativa
        t("menor", "competencia", "no sé", evaluacion=0, nodo="P2"),
        t("menor", "competencia", "¿y tú?", evaluacion=1, nodo="P2", intento=2),             # pregunta: iniciativa
        t("menor", "competencia", "bien", evaluacion=1, nodo="P3"),
    ]
    assert metricas.calcular(turnos, "Preguntas recíprocas").IRC_pct == 40.0      # 2 de 5 (antes: 1 de 5 = 20 %)
    assert metricas.calcular(turnos, "Metáfora").IRC_pct == 20.0                  # en otras competencias, solo «?» y `comparte`
    assert metricas.calcular(turnos).IRC_pct == 20.0


def test_n_figuras_y_nota_de_granularidad():
    """Decisión de Álvaro, 2026-10-12: la granularidad no se corrige; se muestra siempre el nº de figuras por sesión."""
    from scripts.metricas_reales import nota_granularidad
    turnos = [t("menor", "competencia", "a", evaluacion=0, nodo="M1"), t("menor", "competencia", "b", evaluacion=2, nodo="M1", intento=2),
              t("menor", "competencia", "c", evaluacion=2, nodo="M2"), t("menor", "competencia", "d", evaluacion=2, nodo="M3")]
    assert metricas.calcular(turnos).n_figuras == 3
    assert metricas.calcular([t("bot", "apertura", "hola")]).n_figuras == 0
    nota = nota_granularidad([3, 4, 4])
    assert "3-4 figuras" in nota and "25" in nota and "33" in nota           # saltos de 25-33 puntos


def test_informe_excluye_los_amlu_nulos_y_muestra_la_n(cliente, alumno, fake, bd):
    """v3: un aMLU nulo (sin turnos válidos) no entra en medianas ni en el % fuera de rango; el informe da la n de cada métrica."""
    from sqlalchemy import text
    from scripts.metricas_reales import informe
    cid, _ = hasta_primera_figura(cliente, alumno)
    for _ in range(8):                                   # 4 figuras, todo valorado 0 (con ayuda y segundo intento)
        fake.respuestas = [0]
        r = turno(cliente, cid, "asdkj").json()
    assert r["estado"] == "terminada"
    with bd.connect() as c:
        fila = c.execute(text('SELECT amlu, n_turnos_amlu FROM session_data WHERE conversacion_id = :c'), {"c": cid}).mappings().first()
        n_ok = c.execute(text("SELECT count(*) FROM session_data WHERE origen = 'real' AND amlu IS NOT NULL")).scalar()
        n_todas = c.execute(text("SELECT count(*) FROM session_data WHERE origen = 'real'")).scalar()
    assert fila["amlu"] is None and fila["n_turnos_amlu"] == 0
    inf = informe()
    assert inf["n_reales"] == n_todas and inf["metricas"]["aMLU"]["n_real"] == n_ok < n_todas
    assert inf["metricas"]["PEPE"]["n_real"] == n_todas


def test_amlu_pepe_e_irc_son_provisionales_hasta_arreglar_el_prompt_de_valoracion():
    """Decisión de Álvaro, 2026-10-12: mientras el prompt de valoración no esté arreglado, aMLU, PEPE e IRC dependen de un
    evaluador que infravalora/sobrevalora y se tratan como provisionales (en el informe y el dashboard)."""
    from scripts.metricas_reales import etiqueta, notas_provisionales
    assert set(metricas.PROVISIONALES_EVALUADOR) == {"aMLU", "PEPE", "IRC_pct"}
    for col in ("aMLU", "PEPE", "IRC_pct"):
        assert etiqueta(col) == f"{col} (provisional: evaluador)"
    assert etiqueta("latencia_pragmatica_ms") == "latencia_pragmatica_ms"
    assert etiqueta("pct_DET") == "pct_DET (provisional)"                 # %DET sigue con su propio motivo
    assert metricas.columnas_para_clasificador() == ("aMLU", "latencia_pragmatica_ms", "IRC_pct", "PEPE")   # sin cambios
    notas = "\n".join(notas_provisionales())
    assert "evaluador" in notas and "aMLU" in notas and "pct_DET" in notas
