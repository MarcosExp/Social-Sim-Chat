"""Conteos y distribuciones para la cabecera del dashboard (evita traer todas las tablas por JSON)."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.seguridad import exigir_terapeuta
from app.models import ClassifierPrediction, Conversacion, SessionData, StudentProfileSim
from app.schemas import ResumenOut

router = APIRouter(prefix="/resumen", tags=["resumen"], dependencies=[Depends(exigir_terapeuta)])


@router.get("", response_model=ResumenOut)
def resumen(db: Session = Depends(get_db)) -> ResumenOut:
    n = lambda stmt: db.scalar(stmt) or 0            # noqa: E731
    por_tray = dict(db.execute(select(StudentProfileSim.trayectoria_disenada, func.count())
                               .group_by(StudentProfileSim.trayectoria_disenada)).all())
    por_etq = dict(db.execute(select(SessionData.etiqueta_real_disenada, func.count())
                              .where(SessionData.origen == "sintetico").group_by(SessionData.etiqueta_real_disenada)).all())
    return ResumenOut(
        alumnos=n(select(func.count()).select_from(StudentProfileSim)),
        sesiones_sinteticas=n(select(func.count()).select_from(SessionData).where(SessionData.origen == "sintetico")),
        sesiones_reales=n(select(func.count()).select_from(SessionData).where(SessionData.origen == "real")),
        conversaciones=n(select(func.count()).select_from(Conversacion)),
        predicciones=n(select(func.count()).select_from(ClassifierPrediction)),
        versiones_modelo=n(select(func.count(func.distinct(ClassifierPrediction.modelo_version)))),
        ultima_version_modelo=db.scalar(select(func.max(ClassifierPrediction.modelo_version))),
        alumnos_por_trayectoria={k or "sin dato": v for k, v in por_tray.items()},
        sesiones_sinteticas_por_etiqueta={k or "sin dato": v for k, v in por_etq.items()},
    )
