"""Contrato HTTP de /conversaciones y /health con Ollama simulado y Postgres real de pruebas."""
from app.config import settings
from app.guiones import cargar_guiones

G = cargar_guiones()
METAFORA = G.competencias["Metáfora"]


def crear(cliente, alumno, **extra):
    r = cliente.post("/conversaciones", json={"student_id": alumno, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def turno(cliente, cid, mensaje, **extra):
    return cliente.post(f"/conversaciones/{cid}/turnos", json={"mensaje": mensaje, **extra})


def hasta_primera_figura(cliente, alumno):
    c = crear(cliente, alumno, alias="Álvaro")
    cid = c["conversacion_id"]
    assert turno(cliente, cid, "hola").json()["nodo_actual"] == "a2"
    r = turno(cliente, cid, "sí, vale").json()
    assert r["nodo_actual"] == "M1" and r["rama"] == "afirmativa"
    return cid, r


def test_crear_usa_competencia_objetivo_y_alias(cliente, alumno):
    c = crear(cliente, alumno, alias="Álvaro")
    assert c["competencia"] == "Metáfora" and c["personaje"] == METAFORA.personaje
    assert c["estado"] == "en_curso" and c["nodo_actual"] == "a1"
    assert "Álvaro" in c["turno_bot"]["texto"] and "{" not in c["turno_bot"]["texto"]
    assert c["guion_version"] == G.version


def test_conversacion_completa_metafora_todo_correcto(cliente, alumno, fake):
    cid, r = hasta_primera_figura(cliente, alumno)
    assert METAFORA.turnos[0].frase in r["turno_bot"]["texto"]       # texto del guion, literal
    assert fake.llamadas_chat == 0                                    # la apertura no usa LLM
    for i in range(4):
        fake.respuestas = [2]
        r = turno(cliente, cid, "respuesta correcta", latencia_ms=1200).json()
        assert r["evaluacion"] == 2 and r["evaluacion_origen"] == "llm" and r["latencia_ms"] == 1200
        assert r["llm"]["modelo"] == "qwen3:14b" and r["llm"]["intentos"] == 1
    assert r["estado"] == "terminada" and r["turno_bot"]["tipo"] == "cierre"
    assert METAFORA.cierre in r["turno_bot"]["texto"]
    assert fake.llamadas_chat == 4
    d = cliente.get(f"/conversaciones/{cid}").json()
    assert d["estado"] == "terminada" and d["modelo"] == "qwen3:14b"
    ordenes = [t["orden"] for t in d["turnos"]]
    assert ordenes == list(range(1, len(ordenes) + 1))
    assert [t["rol"] for t in d["turnos"]][:3] == ["bot", "menor", "bot"]


def test_latencia_medida_en_servidor_no_incluye_el_tiempo_del_llm(cliente, alumno, fake):
    cid, _ = hasta_primera_figura(cliente, alumno)
    fake.retardo_s, fake.respuestas = 0.5, [0]
    assert turno(cliente, cid, "no sé").status_code == 200           # esta petición tarda ≥ 0,5 s en el servidor
    fake.retardo_s, fake.respuestas = 0, [2]
    r = turno(cliente, cid, "que está contenta").json()               # sin latencia_ms del cliente: la mide el servidor
    assert r["latencia_ms"] < 300


def test_mensaje_en_blanco_se_rechaza_y_no_guarda_turno(cliente, alumno):
    c = crear(cliente, alumno)
    for vacio in ("", "   ", "\n\t"):
        assert turno(cliente, c["conversacion_id"], vacio).status_code == 422
    assert len(cliente.get(f"/conversaciones/{c['conversacion_id']}").json()["turnos"]) == 1   # solo el saludo del bot


def test_ayuda_y_segundo_intento_luego_avanza(cliente, alumno, fake):
    cid, _ = hasta_primera_figura(cliente, alumno)
    fake.respuestas = [0]
    r = turno(cliente, cid, "no sé").json()
    assert r["evaluacion"] == 0 and r["nodo_actual"] == "M1" and r["intento"] == 2
    assert METAFORA.turnos[0].ayuda in r["turno_bot"]["texto"]
    fake.respuestas = [1]
    r = turno(cliente, cid, "puede ser").json()
    assert r["nodo_actual"] == "M2" and r["intento"] == 1               # máx. 2 intentos: se avanza igualmente
    assert METAFORA.turnos[1].frase in r["turno_bot"]["texto"]


def test_rama_negativa_de_apertura(cliente, alumno):
    c = crear(cliente, alumno)
    cid = c["conversacion_id"]
    turno(cliente, cid, "hola")
    r = turno(cliente, cid, "no quiero").json()
    assert r["rama"] == "negativa" and r["nodo_actual"] == "a2A"
    r = turno(cliente, cid, "estoy cansado").json()
    assert r["nodo_actual"] == "a3"
    r = turno(cliente, cid, "hoy he jugado con mi hermano").json()
    assert r["rama"] == "comparte" and r["nodo_actual"] == "M1"


def test_latencia_medida_en_servidor_si_no_se_envia(cliente, alumno):
    c = crear(cliente, alumno)
    r = turno(cliente, c["conversacion_id"], "hola").json()
    assert isinstance(r["latencia_ms"], int) and r["latencia_ms"] >= 0


def test_errores_de_negocio(cliente, alumno, fake):
    assert cliente.post("/conversaciones", json={"student_id": "NO-EXISTE"}).json()["codigo"] == "alumno_no_encontrado"
    r = cliente.post("/conversaciones", json={"student_id": alumno, "competencia": "Inventada"})
    assert r.status_code == 422 and r.json()["codigo"] == "competencia_invalida"
    r = cliente.get("/conversaciones/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404 and r.json()["codigo"] == "conversacion_no_encontrada"
    assert turno(cliente, "00000000-0000-0000-0000-000000000000", "hola").status_code == 404
    c = crear(cliente, alumno)
    assert turno(cliente, c["conversacion_id"], "").status_code == 422        # validación Pydantic
    assert turno(cliente, c["conversacion_id"], "x" * 501).status_code == 422


def test_conversacion_terminada_da_409(cliente, alumno, fake):
    cid, _ = hasta_primera_figura(cliente, alumno)
    fake.respuestas = [2, 2, 2, 2]
    for _ in range(4):
        turno(cliente, cid, "bien")
    r = turno(cliente, cid, "hola otra vez")
    assert r.status_code == 409 and r.json()["codigo"] == "conversacion_terminada"


def test_ollama_caido_503_y_no_se_pierde_el_estado(cliente, alumno, fake, monkeypatch):
    monkeypatch.setattr(settings, "ollama_max_reintentos", 1)
    cid, _ = hasta_primera_figura(cliente, alumno)
    antes = cliente.get(f"/conversaciones/{cid}").json()
    fake.fallos = ["connect", "connect"]
    r = turno(cliente, cid, "es un trueno")
    assert r.status_code == 503
    e = r.json()
    assert e["codigo"] == "llm_no_disponible" and e["reintentable"] is True and "Retry-After" in r.headers
    despues = cliente.get(f"/conversaciones/{cid}").json()
    assert len(despues["turnos"]) == len(antes["turnos"]) and despues["nodo_actual"] == "M1"
    # reintentar el mismo turno ya funciona
    fake.respuestas = [2]
    assert turno(cliente, cid, "es un trueno").status_code == 200


def test_modelo_ausente_503_no_reintentable(cliente, alumno, fake):
    cid, _ = hasta_primera_figura(cliente, alumno)
    fake.fallos = [404]
    e = turno(cliente, cid, "hola").json()
    assert e["codigo"] == "modelo_no_encontrado" and e["reintentable"] is False


def test_json_invalido_se_reintenta_una_vez_y_luego_502(cliente, alumno, fake):
    cid, _ = hasta_primera_figura(cliente, alumno)
    fake.respuestas = ["esto no es json", 2]
    assert turno(cliente, cid, "respuesta").status_code == 200
    assert fake.llamadas_chat == 2
    fake.respuestas = ["basura", {"evaluacion": 7, "reaccion": "x"}]
    r = turno(cliente, cid, "otra")
    assert r.status_code == 502 and r.json()["codigo"] == "respuesta_invalida"


def test_prompt_lleva_figura_y_respuesta_esperada_sin_texto_del_menor_en_system(cliente, alumno, fake):
    cid, _ = hasta_primera_figura(cliente, alumno)
    fake.respuestas = [2]
    turno(cliente, cid, "QUIERO UN CARAMELO GRANDE")      # texto llamativo pero no es una inyección: llega al LLM
    msgs = fake.peticiones[-1]["messages"]
    assert msgs[0]["role"] == "system" and "CARAMELO" not in msgs[0]["content"]
    assert msgs[-1]["role"] == "user" and msgs[-1]["content"].endswith('"""QUIERO UN CARAMELO GRANDE"""')  # delimitado
    assert fake.peticiones[-1]["format"]["required"] == ["analisis", "evaluacion", "reaccion"]


def test_health_ok_y_degradado_con_mensaje_claro(cliente, fake):
    h = cliente.get("/health").json()
    assert h["status"] == "ok" and h["llm"] == "ok" and h["llm_model"] == "qwen3:14b"
    fake.modelos = []
    h = cliente.get("/health").json()
    assert h["status"] == "degraded" and "ollama pull qwen3:14b" in h["llm"] and h["llm_modelo_disponible"] is False
    fake.caido = True
    h = cliente.get("/health").json()
    assert h["status"] == "degraded" and "OLLAMA_HOST" in h["llm"]


def test_dos_envios_simultaneos_a_la_misma_conversacion_no_la_corrompen(bd, alumno, fake):
    import asyncio

    import httpx

    from app.main import app

    async def main():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            cid = (await c.post("/conversaciones", json={"student_id": alumno})).json()["conversacion_id"]
            rs = await asyncio.gather(*[c.post(f"/conversaciones/{cid}/turnos", json={"mensaje": "hola"})
                                        for _ in range(3)])
            return cid, [r.status_code for r in rs], (await c.get(f"/conversaciones/{cid}")).json()

    cid, codigos, d = asyncio.run(main())
    assert codigos == [200, 200, 200]
    ordenes = [t["orden"] for t in d["turnos"]]
    assert ordenes == list(range(1, len(ordenes) + 1))               # sin huecos ni duplicados
    assert len(d["turnos"]) == 1 + 3 * 2


def test_cada_turno_valorado_guarda_la_version_del_evaluador(cliente, alumno, fake):
    from app import conversacion as cv
    cid, r0 = hasta_primera_figura(cliente, alumno)
    fake.respuestas = [2]
    r = turno(cliente, cid, "que está contenta").json()
    version = cv.evaluador_version()
    assert r["evaluador_version"] == version and version.startswith(cv.EVALUADOR_ETIQUETA + "+")
    d = cliente.get(f"/conversaciones/{cid}").json()
    valorados = [t for t in d["turnos"] if t["evaluacion"] is not None]
    assert len(valorados) == 1 and valorados[0]["evaluador_version"] == version
    assert all(t["evaluador_version"] is None for t in d["turnos"] if t["evaluacion"] is None)   # apertura y bot: sin evaluador
    assert r0.get("evaluador_version") is None


def test_la_version_del_evaluador_cambia_con_el_prompt_el_criterio_o_el_schema(monkeypatch):
    from app import conversacion as cv
    base = cv.evaluador_version()
    assert base == cv.evaluador_version()                                    # estable
    monkeypatch.setattr(cv, "PROMPT_EVALUADOR", cv.PROMPT_EVALUADOR + " Criterio nuevo.")
    cambiado_prompt = cv.evaluador_version()
    monkeypatch.undo()
    monkeypatch.setattr(cv, "SCHEMA_EVALUACION", {**cv.SCHEMA_EVALUACION, "required": ["evaluacion"]})
    cambiado_schema = cv.evaluador_version()
    assert len({base, cambiado_prompt, cambiado_schema}) == 3
    assert base.split("+")[0] == cambiado_prompt.split("+")[0] == cv.EVALUADOR_ETIQUETA   # la etiqueta humana no cambia sola


def test_prompt_de_reciprocidad_solo_aparece_en_preguntas_reciprocas():
    """Decisión de Álvaro, 2026-10-12: en «Preguntas recíprocas» compartir algo propio O devolver la pregunta basta (2)."""
    from app import conversacion as cv
    rec = G.competencias["Preguntas recíprocas"]
    p = cv._prompt_sistema(None, G, rec, rec.turnos[0])
    assert "compartir algo propio" in p and "devolver la pregunta" in p and "basta" in p
    met = G.competencias["Metáfora"]
    assert "devolver la pregunta" not in cv._prompt_sistema(None, G, met, met.turnos[0])


def test_criterio_acepta_parafrasis_y_limita_el_cero_ante_la_duda_a_lo_que_no_encaja():
    from app import conversacion as cv
    met = G.competencias["Metáfora"]
    p = cv._prompt_sistema(None, G, met, met.turnos[0])
    assert "paráfrasis" in p
    assert "pon 0 solo" in p and "no encaja" in p          # el 0 ante la duda solo para lo que no encaja
    assert "repetir o reformular la frase figurada" in p and "una persona, un lugar o un momento distinto" in p   # p3: literal y referente = 0
    assert cv.EVALUADOR_ETIQUETA.endswith("-p3")
