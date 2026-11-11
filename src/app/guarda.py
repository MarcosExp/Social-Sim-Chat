"""Guarda de inyecciones en código: se ejecuta ANTES de llamar al LLM evaluador (decisión de Álvaro, 2026-10-12).

Si el mensaje del menor intenta manipular al evaluador (órdenes de ignorar reglas, falsos mensajes del sistema, peticiones de
puntuación, el nombre del campo `evaluacion`…), se valora 0 sin llamar al LLM, `evaluacion_origen = "guarda_inyeccion"` y se
guardan los nombres de los patrones que coinciden (`guarda_patron`). El niño no es penalizado más allá de ese 0: recibe la ayuda
del guion y sigue jugando.

Diseño para evitar falsos positivos con lenguaje infantil:
  - los verbos imperativos (ignora, olvida, puntúa, marca, pon…) solo cuentan al INICIO de una oración (o tras «por favor»,
    «así que»…), no dentro de una frase ("mi hermano ignora las reglas", "mi equipo marca 2 goles");
  - la nota (2/dos) debe ir justo tras el verbo y seguida del fin de la oración o de una conjunción, no de un sustantivo
    ("marca dos goles", "dime dos cosas");
  - «evaluación» con tilde (palabra del colegio) solo cuenta con signo («evaluación: 2») o tras una coma; sin tilde
    («evaluacion», nombre del campo JSON) cuenta siempre.
Las coincidencias se buscan sobre el texto en minúsculas y sin tildes. Los patrones son una defensa adicional al prompt, no su
sustituto: una redacción nueva puede esquivarlos (ver docs/informe-validacion-metricas-reales.md §10).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

_INVISIBLES = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni caracteres invisibles. La «ó» de «evaluación» se marca para distinguirla de «evaluacion»."""
    t = texto.translate(_INVISIBLES).lower().replace("evaluación", "evaluacion_acento")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return re.sub(r"[ \t\r\f\v]+", " ", t)


_EVAL = r"evaluacion(?:_acento)?"
_INICIO = r"(?:^|[.!?¡¿:;,\n(\[]\s*|\b(?:asi que|por favor|please|ahora|entonces|pues)\s+)"
_VERBOS_NOTA = (r"(?:puntua|puntualo|puntuame|evalua|evaluame|evaluala|evalualo|valora|valoralo|califica|calificalo|asigna|otorga|"
                r"devuelve|devuelveme|retorna|responde|contesta|marca|marcame|pon|ponme|ponle|ponlo|da|dame|dale|di|dime|escribe|saca)")
_RELLENO = (r"(?:(?:con|de|como|siempre|ya|me|le|lo|la|tu|mi|a|un|una|el|nota|puntuacion|valoracion|" + _EVAL +
            r"|calificacion|puntos?|maxima|maximo|alta|alto|por favor)\s+){0,4}")
_FIN_NOTA = r"(?=\s*(?:[.!?,;:)\]}]|$)|\s+(?:y|que|porque|pues|ya|gracias|por|sin|asi|ahora|no|si)\b)"
_VERBOS_IGNORA = r"(?:ignora|ignore|ignorad|olvida|olvide|olvidad|desobedece|disregard|forget|omite|override)"
_OBJETO_IGNORA = (r"(?:todo|toda|todas|todos|instrucciones|instruccion|instructions?|reglas|rules?|anteriores?|previous|prior|above|"
                  r"earlier|prompt|sistema|system|lo que)")
_ROLES = (r"(?:evaluador|evaluadora|asistente|juez|jueza|modelo|ia|inteligencia artificial|assistant|judge|evaluator|grader|ai)")

# (nombre, regex sobre el texto normalizado). El orden fija el orden en que se informan.
_PATRONES: list[tuple[str, re.Pattern]] = [
    ("ignora_instrucciones", re.compile(
        _INICIO + r"(?:por favor\s+)?" + _VERBOS_IGNORA + r"\s+(?:\w+\s+){0,3}?" + _OBJETO_IGNORA + r"\b")),
    ("mensaje_de_sistema", re.compile("|".join([
        r"(?:^|\n)\s*[\[<({#*>-]*\s*(?:system|sistema|assistant|asistente|developer|desarrollador|admin|administrador|"
        r"instruccion(?:es)?|instruction|prompt)\s*[\]>)}]*\s*[:\]>]",
        r"\b(?:system|assistant|developer)\s*:",
        r"<\s*/?\s*(?:system|instruccion|instruction|prompt|assistant)\b",
        r"\[\s*(?:instruccion|instruction|system|sistema|nota|aviso)[^\]]{0,80}\]"]))),
    ("ordena_puntuacion", re.compile(
        _INICIO + r"(?:por favor\s+)?" + _VERBOS_NOTA + r"\s+" + _RELLENO + r"(?:2|dos)\b" + _FIN_NOTA)),
    ("afirma_puntuacion", re.compile("|".join([
        r"\b(?:puntuacion|valoracion|calificacion|" + _EVAL + r")\s+(?:(?:correcta|final|esperada|maxima|real|debe\s+ser|"
        r"deberia\s+ser)(?:\s+(?:es|sera|=|:))?|(?:es|sera|=|:))\s*(?:un\s+)?(?:2|dos)\b",
        r"\bnota\s+(?:correcta|final|esperada|debe\s+ser|deberia\s+ser)(?:\s+(?:es|sera|=|:))?\s*(?:un\s+)?(?:2|dos)\b"]))),
    ("token_evaluacion", re.compile("|".join([
        r"\bevaluacion\b(?!_)",                                           # el nombre del campo JSON, sin tilde
        r"\b" + _EVAL + r"\s*[:=]\s*[012]\b",                             # «evaluación: 2», «evaluacion=2»
        r"(?:^|[,;:.]\s*)" + _EVAL + r"\s+[012]\b",                       # «…, evaluación 2»
        r"[\"']\s*(?:reaccion|analisis)\s*[\"']\s*:"]))),
    ("rol_evaluador", re.compile(
        r"\b(?:eres|sois|ahora eres|actua como|comportate como|haz de|finge ser|simula ser|you are|you're|act as|pretend to be|"
        r"pretend you are)\s+(?:un|una|el|la|the|a|an)?\s*(?:muy\s+)?(?:\w+\s+)?" + _ROLES + r"\b")),
    ("ingles_o_jailbreak", re.compile(
        r"\b(?:system\s+prompt|jailbreak|prompt\s+injection|developer\s+mode|do\s+anything\s+now|dan\s+mode|modo\s+desarrollador|"
        r"prompt\s+del\s+sistema)\b")),
]
NOMBRES_PATRONES = tuple(n for n, _ in _PATRONES)


def detectar_inyeccion(mensaje: str) -> list[str]:
    """Nombres de los patrones que coinciden con el mensaje (lista vacía = respuesta normal)."""
    t = normalizar(mensaje)
    return [n for n, rx in _PATRONES if rx.search(t)]


def huella() -> str:
    """Hash corto de los patrones: entra en `evaluador_version` para saber con qué guarda se valoró cada turno."""
    base = "\x1f".join(f"{n}={rx.pattern}" for n, rx in _PATRONES)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:8]
