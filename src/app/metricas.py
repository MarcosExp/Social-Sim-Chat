"""Las 5 métricas por sesión calculadas desde los turnos REALES de una conversación terminada.

Definiciones OPERATIVAS (versión `DEFINICION_VERSION`). Los documentos del proyecto nombran las métricas
pero no fijan la fórmula, así que estas son una propuesta explícita y revisable (docs/metricas-reales.md).
Todas usan las mismas unidades y rangos que el corpus sintético con el que se entrenó el clasificador.

- aMLU  : media de palabras por enunciado del menor, SOLO en turnos de competencia con valoración >= 1 (los 0 no cuentan);
          sin ninguno, NULO (v3: «sin datos» no es «cero palabras»). `n_turnos_amlu` guarda cuántos turnos se usaron (rango típico 1-7).
- LPP   : mediana de `latencia_ms` de TODOS los turnos del menor, apertura incluida (ms). Además `lpp_intento1` y
          `lpp_intento2`: la misma mediana solo en turnos de competencia en el intento 1 y 2 (tras la ayuda).
- IRC % : % de enunciados del menor (apertura y competencia) con iniciativa: hacen una pregunta, comparten algo por su
          cuenta en la apertura (rama `comparte`) o, solo en «Preguntas recíprocas», responden compartiendo algo propio
          (turno de competencia valorado 2, aunque no lleve «?»).
- PEPE  : media de la puntuación POR FIGURA (no por intento), rango 0-2: 2 si el intento 1 vale 2 (sin ayuda); 1 si el
          intento 1 vale 0 o 1 y el intento 2 vale 2 (acierta con la ayuda del guion); 0 en cualquier otro caso.
          Caso ambiguo (revisión clínica): parcial (1) en el intento 1 y sin acertar tras la ayuda puntúa 0.
- %DET  : PROVISIONAL. Mismo valor que `pct_DET_observado_en_turnos` (% de turnos valorados con 2).
          El %DET del diseño es el determinismo RQA entre sesiones, que necesita varias sesiones del
          alumno; todavía no se calcula.

Funciones puras (sin BD) salvo `registrar_sesion`. Desde la migración 008 la sesión se guarda en `session_data` con `origen='real'`.
La valoración que cuenta es la EFECTIVA, `COALESCE(accuracy_corregido, evaluacion)`: la corrección del terapeuta manda y el original se conserva.
"""
from __future__ import annotations

import logging
import re
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Conversacion, SessionData

log = logging.getLogger(__name__)
# v2 (2026-10-12) = decisiones de Álvaro sobre las 7 discrepancias (docs/metricas-reales.md); acumulativa: se aplica entera.
# v3 (2026-10-12) = aMLU nulo (no 0) cuando n_turnos_amlu = 0: «sin datos» no es «cero palabras».
DEFINICION_VERSION = "2026-10-12-v3"
COLUMNAS = ("aMLU", "latencia_pragmatica_ms", "IRC_pct", "PEPE", "pct_DET")
# Métricas cuya definición real aún no equivale a la del corpus (decisión de Álvaro, 2026-10-12). %DET: el diseño es el
# determinismo RQA entre sesiones (necesita varias sesiones por alumno); hoy es el % de turnos con 2.
PROVISIONALES = {"pct_DET": "% de turnos con valoración 2; no es el RQA entre sesiones del diseño"}
RECIPROCAS = "Preguntas recíprocas"
# Dependen de la valoración 0/1/2 del LLM, cuyo prompt está en revisión (infravalora respuestas buenas y se deja manipular;
# informe de validación §10.2). Provisionales hasta que el prompt cumpla los objetivos; borrar esta entrada entonces.
PROVISIONALES_EVALUADOR = {c: "depende de la valoración 0/1/2 del LLM (evaluador p3 sin validar con conversaciones reales ni con la batería 3 revisada)" for c in ("aMLU", "PEPE", "IRC_pct")}
_PALABRA = re.compile(r"\w+", re.UNICODE)


@dataclass
class Metricas:
    aMLU: float | None
    latencia_pragmatica_ms: int | None
    IRC_pct: float | None
    PEPE: float | None
    pct_DET: float | None
    pct_DET_observado_en_turnos: float | None
    n_turnos_menor: int
    n_turnos_evaluados: int
    n_figuras: int | None = None        # desglose (migración 005)
    n_turnos_amlu: int | None = None
    lpp_intento1: int | None = None
    lpp_intento2: int | None = None


def columnas_para_clasificador() -> tuple[str, ...]:
    """Métricas de las sesiones reales (`session_data`, origen real) que pueden alimentar al clasificador sobre sesiones reales: sin las provisionales.
    Revisar cuando haya varias sesiones por alumno para calcular el %DET como RQA (Marcos debe confirmarlo)."""
    return tuple(c for c in COLUMNAS if c not in PROVISIONALES)


def palabras(texto: str) -> int:
    return len(_PALABRA.findall(texto))


def hace_pregunta(texto: str) -> bool:
    return "?" in texto or "¿" in texto


def evaluacion_efectiva(t) -> int | None:
    """COALESCE(accuracy_corregido, evaluacion) del ER. Los turnos de prueba sin esa columna usan la valoración original."""
    corregida = getattr(t, "accuracy_corregido", None)
    return corregida if corregida is not None else t.evaluacion


def iniciativa_turno(t, competencia: str | None) -> bool:
    """Columna `iniciativa` del ER: el menor pregunta, comparte algo propio en la apertura (rama `comparte`) o, solo en
    «Preguntas recíprocas», responde compartiendo algo propio (turno de competencia con valoración efectiva 2)."""
    comparte_algo_propio = competencia == RECIPROCAS and t.tipo == "competencia" and evaluacion_efectiva(t) == 2
    return hace_pregunta(t.texto) or t.rama == "comparte" or comparte_algo_propio


def refrescar_columnas_turno(turnos, competencia: str | None) -> None:
    """Deja `iniciativa` de los turnos del menor coherente con la valoración efectiva (tras una corrección o un recálculo)."""
    for t in turnos:
        if t.rol == "menor":
            t.iniciativa = iniciativa_turno(t, competencia)


def puntuar_figuras(turnos) -> dict[str, int]:
    """Puntuación 0/1/2 de cada figura (nodo de competencia) a partir de los turnos valorados del menor."""
    por_nodo: dict[str, dict[int, int]] = {}
    for t in turnos:
        ev = evaluacion_efectiva(t)
        if t.rol == "menor" and t.tipo == "competencia" and ev is not None:
            por_nodo.setdefault(t.nodo, {}).setdefault(t.intento, ev)
    return {nodo: 2 if ev.get(1) == 2 else 1 if ev.get(2) == 2 else 0 for nodo, ev in por_nodo.items()}


def calcular(turnos, competencia: str | None = None) -> Metricas:
    """`turnos`: objetos/filas con rol, tipo, nodo, intento, texto, evaluacion, rama, latencia_ms (orden cronológico)."""
    menor = [t for t in turnos if t.rol == "menor"]
    comp = [t for t in menor if t.tipo == "competencia"]
    evaluados = [t for t in comp if evaluacion_efectiva(t) is not None]

    validos = [t for t in evaluados if evaluacion_efectiva(t) >= 1]
    amlu = round(statistics.fmean(palabras(t.texto) for t in validos), 2) if validos else None
    def mediana_ms(ts) -> int | None:
        lat = [t.latencia_ms for t in ts if t.latencia_ms is not None]
        return round(statistics.median(lat)) if lat else None

    lpp = mediana_ms(menor)
    lpp1, lpp2 = (mediana_ms([t for t in comp if t.intento == i]) for i in (1, 2))
    iniciativa = sum(1 for t in menor if iniciativa_turno(t, competencia))
    irc = round(100 * iniciativa / len(menor), 1) if menor else None
    figuras = puntuar_figuras(turnos)
    pepe = round(statistics.fmean(figuras.values()), 2) if figuras else None
    det = round(100 * sum(1 for t in evaluados if evaluacion_efectiva(t) == 2) / len(evaluados), 1) if evaluados else None
    return Metricas(amlu, lpp, irc, pepe, det, det, len(menor), len(evaluados), n_turnos_amlu=len(validos), n_figuras=len(figuras),
                    lpp_intento1=lpp1, lpp_intento2=lpp2)


def sesion_de(db: Session, conversacion_id) -> SessionData | None:
    return db.scalar(select(SessionData).where(SessionData.conversacion_id == conversacion_id))


def registrar_sesion(db: Session, conv: Conversacion) -> SessionData | None:
    """Crea (o devuelve la ya existente) la sesión REAL de una conversación terminada y no de prueba en `session_data`.
    El número de sesión continúa la numeración del alumno (UNIQUE student_id, sesion_num del ER)."""
    if conv.estado != "terminada" or conv.es_prueba:
        return None
    previa = sesion_de(db, conv.conversacion_id)
    if previa is not None:
        return previa
    for _ in range(3):  # carrera improbable: dos conversaciones del mismo alumno terminando a la vez
        refrescar_columnas_turno(conv.turnos, conv.competencia)
        m = calcular(conv.turnos, conv.competencia)
        n = db.scalar(select(func.coalesce(func.max(SessionData.sesion_num), 0)).where(
            SessionData.student_id == conv.student_id)) + 1
        fila = SessionData(
            origen="real", conversacion_id=conv.conversacion_id, student_id=conv.student_id, sesion_num=n,
            competencia=conv.competencia, personaje=conv.personaje, fecha=datetime.now(timezone.utc).date(),
            definicion_version=DEFINICION_VERSION, **asdict(m))
        db.add(fila)
        try:
            db.commit()
            return fila
        except IntegrityError:
            db.rollback()
    log.error("No se pudo registrar la sesión real de %s", conv.conversacion_id)
    return None


def recalcular_sesion(db: Session, conv: Conversacion, sesion: SessionData) -> SessionData:
    """Recalcula con la definición vigente las columnas de turno y las métricas de una sesión real ya registrada.
    Lo usan `scripts.metricas_reales --recalcular` y las correcciones del terapeuta por API (el dashboard no toca la BD)."""
    refrescar_columnas_turno(conv.turnos, conv.competencia)       # iniciativa coherente con la valoración efectiva
    for k, v in asdict(calcular(conv.turnos, conv.competencia)).items():
        setattr(sesion, k, v)
    sesion.definicion_version = DEFINICION_VERSION
    db.commit()
    return sesion
