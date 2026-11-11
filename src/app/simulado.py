"""Modo simulado (`LLM_PROVIDER=simulado`): valoración 0/1/2 por REGLAS, sin LLM ni GPU.

Para qué sirve (NF2, historia 11): poder ejecutar y evaluar el prototipo sin GPU (`docker compose up` en cualquier portátil) y
tener un plan B para la defensa. Para qué NO sirve: no es el evaluador del producto. Entiende los 13 turnos de los guiones
cerrados mediante léxico escrito a mano; una respuesta fuera de lo previsto la valora peor de lo que lo haría una persona o el
LLM. Por eso:
  - sus valoraciones llevan `evaluacion_origen = 'heuristica'`, `evaluador_version = 'simulado-…'` y la conversación `modelo = 'simulado'`;
  - por defecto las conversaciones simuladas son `es_prueba` (no generan sesión real ni métricas): no mezclar datos simulados
    con datos reales (ver `SIMULADO_REGISTRA_SESIONES` en `app/config.py`);
  - su calidad se mide con las baterías (`LLM_PROVIDER=simulado python -m scripts.bateria_valoracion`), resultado en `docs/modo-simulado.md`.

El guion sigue mandando: el texto de las figuras y de las ayudas sale literal del guion; aquí solo se decide el 0/1/2 y se escribe
una reacción breve y fija. La guarda de inyecciones (`app/guarda.py`) se aplica ANTES, igual que con el LLM.

Reglas, en este orden (cada figura trae su léxico en `FIGURAS`; las que no están usan la respuesta esperada del guion):
  1. Eco: repetir la frase del personaje (todas las palabras ya estaban en ella) -> 0.
  2. Significado (metáforas, sarcasmo, deixis 2-3):
       idea esperada (`core`, sin negar)      -> 2
       interpretación literal (`literal`)      -> 0
       idea contraria (`opuesto`, sin negar)   -> 0
       idea contraria negada o vaga (`vago`)   -> 1
       otra cosa                               -> 0
  3. Estructura (preguntas recíprocas y deixis 1): compartir algo propio o devolver la pregunta -> 2; una palabra que responde -> 1;
     rechazo, vacío, 3.ª persona o fuera de tema -> 0.
"""
from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from dataclasses import dataclass, field

from app import llm_client

ETIQUETA = "simulado-2026-10-25"
MODELO = "simulado"
REACCION_BAJA = "Gracias por tu respuesta."


# --------------------------------------------------------------------------- texto
def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes (la ñ se conserva como n) y solo letras, dígitos, espacios y signos de pregunta."""
    s = unicodedata.normalize("NFD", texto.lower().replace("ñ", "\x01"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("\x01", "n")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9?¿ ]", " ", s)).strip()


_PARADA = set("""a al algo ante con contra de del desde e el ella en entre es esta estan este esto la las le les lo los me mi mis muy
no o para pero por que se si sin su sus te tu un una uno unos unas y ya hoy""".split())


def _palabras(texto: str) -> list[str]:
    return [p for p in normalizar(texto).replace("?", " ").replace("¿", " ").split() if p not in _PARADA]


_NEGACION = {"no", "nunca", "tampoco", "ni"}


def _busca(patrones: tuple[str, ...], t: str) -> tuple[bool, bool]:
    """(hay coincidencia sin negar, hay coincidencia negada). Negada = «no/nunca/tampoco/ni» en las 2 palabras anteriores o «nada» justo antes."""
    limpia = negada = False
    for p in patrones:
        for m in re.finditer(p, t):
            previas = t[:m.start()].split()
            if _NEGACION & set(previas[-2:]) or previas[-1:] == ["nada"]:
                negada = True
            else:
                limpia = True
    return limpia, negada


# --------------------------------------------------------------------------- léxico de los 13 turnos
@dataclass(frozen=True)
class Figura:
    core: tuple[str, ...] = ()      # expresan la idea esperada (nivel 2)
    vago: tuple[str, ...] = ()      # idea vaga o parcial (nivel 1)
    opuesto: tuple[str, ...] = ()   # idea contraria (nivel 0; negada pasa a vaga)
    literal: tuple[str, ...] = ()   # interpretación literal de la expresión (nivel 0)
    tipo: str = "significado"       # significado | recíproca | yo
    propio: tuple[str, ...] = ()    # (recíproca) algo propio sobre lo que se preguntó
    corta: tuple[str, ...] = ()     # (recíproca) respuesta corta que sí contesta (nivel 1)
    extra: dict = field(default_factory=dict)


FIGURAS: dict[str, Figura] = {
    # --- Metáforas
    "M1": Figura(core=(r"\bcontent\w*", r"\bfeliz\w*", r"\balegr\w*", r"\beufor\w*", r"\bemociona\w*", r"\bilusion\w*"),
                 vago=(r"\bbien\b", r"\bbonit\w*", r"\bguay\b"),
                 opuesto=(r"\btriste\w*", r"\benfad\w*", r"\benoja\w*", r"\bmal\b", r"\bllor\w*", r"\brabia\b", r"\basust\w*"),
                 literal=(r"\bexplot\w*", r"\bbomba\w*", r"\bpedazo\w*", r"\brompe\w*", r"\bestall\w*")),
    "M2": Figura(core=(r"\bnervio\w*", r"\bansio\w*", r"\binquiet\w*", r"\bpreocup\w*", r"\bagobi\w*", r"\bintranquil\w*",
                       r"\bangusti\w*"),
                 vago=(r"\bpasa algo\b", r"\btripa\b", r"\bbarriga\b", r"\bestomago\b", r"\braro\b", r"\bsiente algo\b"),
                 opuesto=(r"\btranquil\w*", r"\brelaj\w*", r"\bcalm\w*", r"\bcontent\w*", r"\bfeliz\w*", r"\balegr\w*"),
                 literal=(r"\bmariposa\w*", r"\btrag\w*")),
    "M3": Figura(core=(r"\bfacil\w*", r"\bsencill\w*", r"\bsimple\w*", r"\bsin esfuerzo\b", r"\bpoco esfuerzo\b",
                       r"\bchupado\b", r"\btirado\b"),
                 vago=(r"\bnormal\b", r"\bbien\b", r"\bno es (muy |nada )?(dificil|complicad\w*)",
                       r"\bno esta (muy |nada )?(dificil|complicad\w*)"),
                 opuesto=(r"\bdificil\w*", r"\bcomplica\w*", r"\bduro\b", r"\bimposible\b", r"\bpesad\w*"),
                 literal=(r"\bpan\b", r"\bcom(er|ido|ida|e|en)\b")),
    "M4": Figura(core=(r"\basust\w*", r"\bmiedo\w*", r"\bsusto\w*", r"\bsorprend\w*", r"\baterr\w*", r"\bespant\w*",
                       r"\bterror\w*", r"\bimpact\w*"),
                 opuesto=(r"\bcontent\w*", r"\bfeliz\w*", r"\balegr\w*", r"\btranquil\w*", r"\benfad\w*"),
                 literal=(r"\bcongel\w*", r"\bhielo\b", r"\bfria\b", r"\bhelad\w*", r"\bsangre\b")),
    # --- Sarcasmo
    "S1": Figura(core=(r"\benfad\w*", r"\bmoles\w*", r"\bfastidi\w*", r"\brabia\b", r"\benoja\w*", r"\bharto\b", r"\bharta\b",
                       r"\bcabre\w*", r"\bfurios\w*", r"\birrit\w*", r"\bdisgust\w*", r"\bfrustr\w*", r"\bchafad\w*", r"\brencor\w*"),
                 vago=(r"\bmal\b", r"\btriste\w*", r"\bdecepcion\w*", r"\bno le gusta\b"),
                 opuesto=(r"\bcontent\w*", r"\bfeliz\w*", r"\balegr\w*", r"\bgenial\b", r"\bgusta\b", r"\bencanta\b", r"\bbien\b")),
    "S2": Figura(core=(r"\bfrustr\w*", r"\benfad\w*", r"\bmoles\w*", r"\brabia\b", r"\bfastidi\w*", r"\bfatal\b",
                       r"\bno se le da (muy )?bien\b", r"\bno lo hace bien\b", r"\bno le sale\b", r"\b(lo hace|le sale|hace) mal\b",
                       r"\bno quiero (seguir|jugar|continuar)\b", r"\bme quiero ir\b", r"\bno me va a gust\w*"),
                 vago=(r"\bmal\b", r"\btriste\w*", r"\bdecepcion\w*", r"\bda igual\b", r"\bno me importa\b"),
                 opuesto=(r"\bse le da (muy )?bien\b", r"\bfenomenal\b", r"\bgenial\b", r"\bjuega muy bien\b", r"\bha ganado\b",
                          r"\bgana\b", r"\bcontent\w*", r"\bfeliz\w*", r"\bbien\b")),
    "S3": Figura(core=(r"\bmala suerte\b", r"\bdecepcion\w*", r"\btriste\w*", r"\bfastidi\w*", r"\benfad\w*", r"\bmoles\w*",
                       r"\bdesilusion\w*", r"\bpena\b", r"\blastima\b"),
                 vago=(r"\bmal\b", r"\bno le gusta\b", r"\bno les gusta\b"),
                 opuesto=(r"\bmucha suerte\b", r"\bbuena suerte\b", r"\bcontent\w*", r"\bfeliz\w*", r"\balegr\w*", r"\bgusta\b")),
    # --- Deixis
    "D2": Figura(core=(r"\ben este momento\b", r"\bahora mismo\b", r"\bya mismo\b", r"^(que )?(es )?ya$", r"\b(el|este|ese) momento\b",
                       r"\bcuando (estamos|hablamos|yo diga)\b", r"\bpresente\b"),
                 vago=(r"\bpronto\b", r"\bdentro de poco\b", r"\bahora\b"),
                 opuesto=(r"\bmanana\b", r"\bayer\b", r"\bluego\b", r"\bdespues\b", r"\bantes\b")),
    "D3": Figura(core=(r"\bcasa (del|de el|donde)\b", r"\bsitio donde\b", r"\blugar donde\b", r"\bdonde (esta|vive)\b",
                       r"\bsu casa\b", r"\bcasa del\b"),
                 vago=(r"\bla casa\b", r"\bperr\w*"),
                 opuesto=(r"\bmi casa\b", r"\btu casa\b", r"\bescuela\b", r"\bcole\w*", r"\bparque\b", r"\bmanana\b")),
    # --- Preguntas recíprocas y deixis 1: reglas de estructura
    "P1": Figura(tipo="recíproca",
                 propio=(r"\byo\b", r"\bme (gusta|gustan|encanta|encantan)\b", r"\b(he|hemos) \w+(ado|ido)\b",
                         r"\b(jugue|fui|hice|dibuje|comi|vi|estuve|corri|monte|lei|pinte|salte|hable)\b", r"\bmi \w+"),
                 corta=(r"\bbien\b", r"\bmal\b", r"\bnormal\b", r"\bregular\b")),
    "P2": Figura(tipo="recíproca",
                 propio=(r"\byo\b", r"\bmi (color|favorito)\w*", r"\bme (gusta|gustan|encanta|encantan)\b"),
                 corta=(r"\b(rojo|roja|azul|verde|amarill\w*|naranja|morad\w*|rosa|rosad\w*|negro|negra|blanc\w*|gris|marron)\b",)),
    "P3": Figura(tipo="recíproca",
                 propio=(r"\byo\b", r"\bme (siento|encuentro|gusta)\b", r"\bestoy\b", r"\bsoy\b"),
                 corta=(r"\bbien\b", r"\bmal\b", r"\bnormal\b", r"\bregular\b", r"\bcansad\w*", r"\bcontent\w*", r"\bfeliz\w*")),
    "D1": Figura(tipo="yo"),
}

# Preguntas dirigidas al personaje (devolver la pregunta).
_PREGUNTA = re.compile(r"[?¿]|^(y tu|tu que|y a ti|cual es el tuyo|y el tuyo|por que te)\b")
_ABANDONO = re.compile(r"\b(no (quiero|me apetece|tengo ganas|puedo)|ahora no|paso|qu(e|é) mas da|dejame|dejalo)\b")
_VACIA = {"ok", "vale", "si", "no", "nose", "a", "bueno", "ya esta", "no se", "ni idea", "nada", "mm", "hm"}


def _eco(texto: str, frase: str) -> bool:
    """Repite la frase del personaje: 3 o más palabras con contenido y casi todas ya estaban en ella."""
    p = _palabras(texto)
    f = set(_palabras(frase))
    if len(p) < 3 or sum(w in f for w in p) / len(p) < 0.8:
        return False
    def pares(x):
        w = normalizar(x).replace("?", " ").replace("¿", " ").split()
        return set(zip(w, w[1:]))
    mios = pares(texto)
    return bool(mios) and len(mios & pares(frase)) / len(mios) >= 0.5


_DUDA = re.compile(r"\bno estoy segur[oa]\b|\bno se por que\b")


def _significado(f: Figura, t: str) -> int:
    core, _ = _busca(f.core, t)
    if core:
        if _busca(f.opuesto, t)[0] or _DUDA.search(t):          # se contradice o dice que no está seguro: solo parcial
            return 1
        return 2
    if _busca(f.literal, t)[0]:
        return 0
    opuesto, opuesto_negado = _busca(f.opuesto, t)
    if opuesto:
        return 0
    vago, vago_negado = _busca(f.vago, t)
    return 1 if (opuesto_negado or vago or vago_negado) else 0


def _estructura(f: Figura, t: str, texto: str, frase: str) -> int:
    if f.tipo == "yo":                                           # D1: relatar algo propio con «yo»
        if re.search(r"\b(tu|el|ella|ellos|ustedes)\b (fue|fuiste|fueron|hizo|hiciste|jugo|jugaste|comio|comiste)\b", t) \
                and not re.search(r"\byo\b", t):
            return 0
        negado = bool(re.search(r"\bnada\b|\bno (fui|fuimos|jugue|hice|comi|desayune|vi|estuve|he|hemos)\b", t))
        if re.search(r"\byo\b", t) and len(t.split()) >= 3 and not negado:
            return 2
        primera = re.search(r"\b(fui|fuimos|jugue|jugamos|hice|hicimos|comi|comimos|desayune|vi|vimos|estuve|estuvimos|"
                            r"hemos|he) ", t + " ") or re.search(r"\byo\b", t)
        return 1 if primera else 0
    # recíprocas
    if _ABANDONO.search(t) or t in _VACIA or not t:
        return 0
    if re.search(r"\b(tu|usted) (estas|eres|has|fuiste|jugaste|tienes)\b", t) and "?" not in texto:
        return 0                                                 # habla del personaje, no de sí mismo
    pregunta = bool(_PREGUNTA.search(t if "?" not in texto else texto.lower())) and \
        (bool(re.search(r"\b(tu|tuyo|tuya|ti|te|usted)\b|^y ", t)) or bool(set(_palabras(frase)) & set(_palabras(texto))))
    propio = _busca(f.propio, t)[0] or bool(re.search(r"\byo\b", t))
    corta = _busca(f.corta, t)[0] and len(t.split()) <= 3
    negativo = bool(re.match(r"^no\b", t))
    if pregunta and len(t.split()) >= 2:
        return 2
    if propio and not negativo:
        return 2
    if corta or (propio and negativo):
        return 1
    return 0


def _generica(correcta: str, t: str) -> int:
    """Turnos sin léxico propio (guion nuevo): cobertura de las palabras de la respuesta esperada (primera alternativa)."""
    esperadas = set(_palabras(correcta.split("/")[0]))
    if not esperadas:
        return 0
    dichas = {p[:5] for p in _palabras(t)}
    cubiertas = sum(e[:5] in dichas for e in esperadas) / len(esperadas)
    return 2 if cubiertas >= 0.6 else 1 if cubiertas >= 0.3 else 0


_INSTRUCCION = re.compile(r"\b(cambia\w*|ponme|dame|debe dar|debes dar|tienes que dar|nota|notas|puntuacion|puntua\w*|sistema|"
                          r"evaluador|valoracion|profesor me dijo|ignora\w*)\b")


def _degenerada(t: str) -> bool:
    """Una misma palabra con contenido repetida 3 o más veces."""
    from collections import Counter
    c = Counter(w for w in t.split() if len(w) > 2)
    return bool(c) and max(c.values()) >= 3


def valorar_regla(turno, mensaje: str) -> int:
    """0/1/2 para la respuesta `mensaje` al turno del guion `turno` (con `id`, `frase`/`texto`, `correcta`)."""
    t = normalizar(mensaje)
    if not t.replace("?", "").strip() or _INSTRUCCION.search(t) or _degenerada(t):
        return 0
    frase = getattr(turno, "frase", None) or turno.texto
    if _eco(mensaje, frase):
        return 0
    f = FIGURAS.get(turno.id)
    if f is None:
        return _generica(turno.correcta, t)
    if f.tipo == "significado":
        return _significado(f, t)
    return _estructura(f, t, mensaje, frase)


def reaccion(evaluacion: int, turno) -> str:
    """Reacción breve y fija: con 2 dice qué ha entendido (la respuesta esperada del guion); con 0/1 agradece sin decir que falló."""
    if evaluacion == 2:
        base = turno.correcta.split("/")[0].strip().rstrip(".")
        if base.lower().startswith("que "):
            return f"¡Muy bien! Has entendido {base[0].lower() + base[1:]}."
        return "¡Muy bien! Justo eso."
    return REACCION_BAJA


# --------------------------------------------------------------------------- integración con el motor
def valorar(turno, mensaje: str) -> tuple[int, str, llm_client.ChatResultado]:
    """(evaluacion, reaccion, ChatResultado) con la misma forma que devuelve `conversacion.evaluar_con_llm`."""
    inicio = time.perf_counter()
    ev = valorar_regla(turno, mensaje)
    ms = round((time.perf_counter() - inicio) * 1000)
    return ev, reaccion(ev, turno), llm_client.ChatResultado(
        texto="", modelo=MODELO, prompt_tokens=None, eval_tokens=None, ollama_ms=None, carga_ms=None,
        espera_cola_ms=0, intentos=1, ms_total=ms)


def version() -> str:
    """Identificador del evaluador simulado: etiqueta + hash (8 hex) del léxico y las reglas (cambia si cambian)."""
    base = repr(sorted((k, repr(v)) for k, v in FIGURAS.items())) + REACCION_BAJA + _PREGUNTA.pattern + _ABANDONO.pattern
    return f"{ETIQUETA}+{hashlib.sha256(base.encode('utf-8')).hexdigest()[:8]}"


def diagnostico() -> dict:
    """Estado para /health: el modo simulado no depende de ningún servidor."""
    return {"estado": "ok", "detalle": "modo simulado: valoración 0/1/2 por reglas, sin LLM (no es el evaluador del producto)",
            "modelo": MODELO, "modelo_disponible": True}
