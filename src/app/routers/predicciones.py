from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.seguridad import exigir_terapeuta
from app.models import ClassifierPrediction, SessionData
from app.schemas import PrediccionOut

router = APIRouter(prefix="/predicciones", tags=["predicciones"], dependencies=[Depends(exigir_terapeuta)])


@router.get("", response_model=list[PrediccionOut])
def listar(
    student_id: str | None = Query(default=None),
    modelo_version: str | None = Query(default=None, description="Por defecto, la última versión de cada origen."),
    todas_las_versiones: bool = Query(default=False),
    origen: Literal["sintetico", "real"] | None = Query(default=None, description="Origen de la sesión predicha."),
    db: Session = Depends(get_db),
) -> list[ClassifierPrediction]:
    """Predicciones del clasificador.

    Las del corpus sintético las calcula `train_classifier` por lotes (validación cruzada, modelo de 15 features). Las de las
    sesiones reales las calcula el backend al cerrar cada sesión con el modelo de servicio (sin %DET; su versión lleva «sinDET»)
    y son orientativas (`GET /students/{id}/prediccion` da los avisos). Son versiones distintas: por defecto se devuelve la
    última de CADA origen, para que una no oculte a la otra."""
    stmt = (select(ClassifierPrediction).join(SessionData, SessionData.session_id == ClassifierPrediction.session_id)
            .order_by(ClassifierPrediction.student_id, ClassifierPrediction.session_id))
    if student_id is not None:
        stmt = stmt.where(ClassifierPrediction.student_id == student_id)
    if origen is not None:
        stmt = stmt.where(SessionData.origen == origen)
    if modelo_version is not None:
        stmt = stmt.where(ClassifierPrediction.modelo_version == modelo_version)
    elif not todas_las_versiones:
        def ultima(o: str):
            return (select(func.max(ClassifierPrediction.modelo_version))
                    .join(SessionData, SessionData.session_id == ClassifierPrediction.session_id)
                    .where(SessionData.origen == o).scalar_subquery())
        stmt = stmt.where(or_(*[(SessionData.origen == o) & (ClassifierPrediction.modelo_version == ultima(o))
                                for o in ("sintetico", "real")]))
    return list(db.scalars(stmt))
