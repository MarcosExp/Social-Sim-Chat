"""Predicción del clasificador sobre sesiones REALES (modelo de servicio, sin %DET).

Alcance acordado con Marcos el 19/11/2026 (devolución del NF3: «cerrar el enlace con el servicio»):

- **Modelo:** el bloque `servicio` de `models/classifier.joblib`, que escribe `scripts.train_classifier`: mismas sesiones
  sintéticas y mismos folds que el modelo evaluado, sin las métricas provisionales (`metricas.PROVISIONALES`, hoy %DET).
  Su `modelo_version` lleva `sinDET`.
- **Entrada:** las sesiones reales del alumno (`origen = 'real'`), nunca las sintéticas. Las features son de ventana
  (`ml/features.py`, sin modificar): las últimas `ventana` sesiones del alumno EN ESA COMPETENCIA y la diferencia con sus
  `n_base` primeras. Por eso las sesiones 1 a `ventana - 1` de cada competencia no tienen predicción, como en el entrenamiento.
- **Alerta:** tres sesiones seguidas predichas como no-progreso (misma regla que `retraso_deteccion` de Marcos).
- **Carga:** al arrancar el backend, y de nuevo si el fichero cambia (`make train` se ejecuta con el backend ya en marcha).
  Si no hay modelo o no coincide con lo que construye la inferencia, la API sigue funcionando y `/health` lo dice.

LÍMITE QUE NO CAMBIA: el modelo se entrenó solo con datos sintéticos y las escalas de las sesiones reales pueden no coincidir
con las del corpus. La predicción es ORIENTATIVA y no está validada con menores reales (`AVISOS`).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app import ml_config
from app.models import ClassifierPrediction, SessionData

log = logging.getLogger(__name__)

RUTA = Path(__file__).resolve().parent.parent / "models" / "classifier.joblib"
RACHA_ALERTA = 3      # sesiones seguidas de no-progreso (ml/evaluar_corpus.py::retraso_deteccion)

AVISOS = (
    "Predicción ORIENTATIVA: el modelo se entrenó solo con datos sintéticos y no está validado con menores reales.",
    "Las escalas de las métricas de las sesiones reales pueden no coincidir con las del corpus sintético; "
    "`fuera_de_rango` señala las features que caen fuera de lo que vio el modelo al entrenar.",
    "El modelo de servicio no usa %DET (provisional en sesiones reales); se midió sobre el corpus sintético.",
    "aMLU, PEPE e IRC dependen del evaluador 0/1/2, aún sin validar con conversaciones reales ni con terapeutas.",
)

_cerrojo = threading.Lock()
_cache: dict = {"firma": None, "paquete": None, "motivo": "todavía no se ha intentado cargar el modelo"}


@dataclass
class PrediccionSesion:
    session_id: object
    sesion_num: int
    competencia: str
    etiqueta_predicha: str
    confianza: float
    es_estancamiento_operacional: bool
    fuera_de_rango: list[str] = field(default_factory=list)


@dataclass
class Resultado:
    modelo_version: str | None
    predicciones: list[PrediccionSesion]
    motivos: list[str]            # por qué no hay predicción (del alumno o de alguna de sus sesiones)
    sesiones_reales: int


def _validar(paquete: object) -> tuple[dict | None, str]:
    """El joblib debe traer el modelo de servicio y la MISMA lista de features que construye la inferencia."""
    servicio = paquete.get("servicio") if isinstance(paquete, dict) else None
    if not isinstance(servicio, dict):
        return None, "classifier.joblib no trae el modelo de servicio (clave `servicio`): vuelve a ejecutar `make train`"
    esperadas = ml_config.columnas_features_servicio()
    if list(servicio.get("features", [])) != esperadas:
        return None, ("las features del modelo de servicio no coinciden con las que construye la inferencia "
                      f"({len(servicio.get('features', []))} frente a {len(esperadas)}): vuelve a ejecutar `make train`")
    p = ml_config.config_servicio()["features"]
    if (servicio.get("ventana"), servicio.get("n_base")) != (int(p["ventana"]), int(p["n_base"])):
        return None, "la ventana o la línea base del modelo de servicio no coinciden con la configuración: vuelve a ejecutar `make train`"
    if ml_config.SUFIJO_VERSION_SERVICIO not in str(servicio.get("version", "")):
        return None, "la versión del modelo de servicio no indica que va sin %DET"
    return servicio, ""


def cargar() -> dict | None:
    """Devuelve el modelo de servicio (o None). Lee el fichero solo si es nuevo o ha cambiado. Nunca lanza."""
    with _cerrojo:
        try:
            st = RUTA.stat()
        except OSError:
            _cache.update(firma=None, paquete=None, motivo=f"no existe {RUTA.name}: ejecuta `make train`")
            return None
        firma = (str(RUTA), st.st_mtime_ns, st.st_size)
        if firma == _cache["firma"]:
            return _cache["paquete"]
        try:
            import joblib
            paquete, motivo = _validar(joblib.load(RUTA))
        except Exception as exc:  # noqa: BLE001 — un fichero corrupto o de otra versión no debe tumbar la API
            paquete, motivo = None, f"no se pudo leer {RUTA.name}: {type(exc).__name__}"
            log.exception("No se pudo cargar el clasificador de %s", RUTA)
        _cache.update(firma=firma, paquete=paquete, motivo=motivo)
        if paquete is not None:
            log.info("Clasificador de servicio cargado: %s", paquete["version"])
        return paquete


def estado() -> str:
    """Texto para `/health`: «ok: <versión>» o «no disponible: <motivo>». No afecta al estado general de la API."""
    paquete = cargar()
    return f"ok: {paquete['version']}" if paquete is not None else f"no disponible: {_cache['motivo']}"


def _sesiones_reales(db: Session, student_id: str) -> list[SessionData]:
    # ANTIFUGA en inferencia: la ventana se construye solo con sesiones reales (ADR-001).
    return list(db.scalars(select(SessionData).where(SessionData.student_id == student_id, SessionData.origen == "real")
                           .order_by(SessionData.sesion_num)))


def calcular(db: Session, student_id: str) -> Resultado:
    """Predicciones de todas las sesiones reales del alumno que tienen ventana completa. No escribe en la BD."""
    sesiones = _sesiones_reales(db, student_id)
    paquete = cargar()
    if paquete is None:
        return Resultado(None, [], [f"El clasificador no está disponible: {_cache['motivo']}."], len(sesiones))
    ventana, cols, mets = paquete["ventana"], paquete["features"], paquete["metricas"]
    motivos: list[str] = []
    por_competencia: dict[str, int] = {}
    for s in sesiones:
        por_competencia[s.competencia] = por_competencia.get(s.competencia, 0) + 1
    if not any(n >= ventana for n in por_competencia.values()):
        detalle = ", ".join(f"{c}: {n}" for c, n in sorted(por_competencia.items())) or "ninguna"
        motivos.append(f"Hacen falta {ventana} sesiones reales del alumno en una misma competencia para formar una ventana "
                       f"(hay {detalle}). Las sesiones sintéticas no cuentan, aunque la numeración continúe.")
        return Resultado(paquete["version"], [], motivos, len(sesiones))

    import numpy as np
    import pandas as pd

    df = pd.DataFrame([{"alumno_id": s.student_id, "competencia": s.competencia, "sesion": s.sesion_num, "session_id": s.session_id,
                        **{m: (None if getattr(s, m) is None else float(getattr(s, m))) for m in mets}} for s in sesiones])
    for m in mets:
        df[m] = df[m].astype(float)
    F = ml_config.construir_features_servicio(df)
    incompletas = F[cols].isna().any(axis=1)
    if incompletas.any():
        nums = ", ".join(str(int(n)) for n in F.loc[incompletas, "sesion"])
        motivos.append(f"Sin predicción en la(s) sesión(es) {nums}: falta alguna métrica en su ventana o en la línea base "
                       "(por ejemplo, aMLU nulo cuando ningún turno fue válido).")
    F = F[~incompletas].reset_index(drop=True)
    if F.empty:
        return Resultado(paquete["version"], [], motivos, len(sesiones))

    X = F[cols].to_numpy()
    modelo = paquete["modelo"]
    pred = modelo.predict(X)
    conf = modelo.predict_proba(X).max(axis=1)
    F["_np"] = pred != "progreso"
    alerta = (F.sort_values(["competencia", "sesion"]).groupby("competencia")["_np"]
              .transform(lambda s: s.rolling(RACHA_ALERTA).sum() == RACHA_ALERTA).reindex(F.index).fillna(False).to_numpy())
    rangos = paquete.get("rango_entrenamiento", {})
    eps = 1e-9
    salida = []
    for i in range(len(F)):
        fuera = [c for c in cols if c in rangos and not (rangos[c][0] - eps <= float(F[c].iat[i]) <= rangos[c][1] + eps)]
        salida.append(PrediccionSesion(F["session_id"].iat[i], int(F["sesion"].iat[i]), F["competencia"].iat[i], str(pred[i]),
                                       round(float(np.clip(conf[i], 0, 1)), 3), bool(alerta[i]), fuera))
    salida.sort(key=lambda p: p.sesion_num)
    return Resultado(paquete["version"], salida, motivos, len(sesiones))


def guardar(db: Session, student_id: str) -> int:
    """Recalcula y guarda las predicciones de las sesiones reales del alumno con el modelo cargado (hace commit).

    Se recalculan todas, no solo la última: una corrección del terapeuta cambia las métricas de una sesión y, con ellas, las
    ventanas de las siguientes y la línea base. El historial por versión se conserva (`UNIQUE (session_id, modelo_version)`);
    solo se reemplazan las filas de la versión cargada. `session_data` guarda la última predicción, como en el corpus."""
    r = calcular(db, student_id)
    if r.modelo_version is None:
        return 0
    ids = [s.session_id for s in _sesiones_reales(db, student_id)]
    if not ids:
        return 0
    db.execute(delete(ClassifierPrediction).where(ClassifierPrediction.session_id.in_(ids),
                                                  ClassifierPrediction.modelo_version == r.modelo_version))
    db.execute(update(SessionData).where(SessionData.session_id.in_(ids)).values(etiqueta_prediccion=None, confianza_prediccion=None))
    for p in r.predicciones:
        db.add(ClassifierPrediction(student_id=student_id, session_id=p.session_id, modelo_version=r.modelo_version,
                                    etiqueta_predicha=p.etiqueta_predicha, confianza=p.confianza,
                                    es_estancamiento_operacional=p.es_estancamiento_operacional))
        db.execute(update(SessionData).where(SessionData.session_id == p.session_id)
                   .values(etiqueta_prediccion=p.etiqueta_predicha, confianza_prediccion=p.confianza))
    db.commit()
    return len(r.predicciones)


def guardar_sin_romper(db: Session, student_id: str) -> None:
    """Para el cierre de sesión y las correcciones: la predicción nunca rompe la conversación ni la corrección."""
    try:
        guardar(db, student_id)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("No se pudo guardar la predicción de las sesiones reales de %s", student_id)


def guardar_todos(db: Session) -> int:
    """Tras `make train`: vuelve a predecir las sesiones reales de todos los alumnos con la versión recién entrenada."""
    alumnos = list(db.scalars(select(SessionData.student_id).where(SessionData.origen == "real").distinct()))
    return sum(guardar(db, a) for a in alumnos)
