from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.seguridad import exigir_terapeuta
from app.models import ClassifierPrediction
from app.schemas import PrediccionOut

router = APIRouter(prefix="/predicciones", tags=["predicciones"], dependencies=[Depends(exigir_terapeuta)])


@router.get("", response_model=list[PrediccionOut])
def listar(
    student_id: str | None = Query(default=None),
    modelo_version: str | None = Query(default=None, description="Por defecto, la última versión entrenada."),
    todas_las_versiones: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[ClassifierPrediction]:
    """Predicciones del clasificador (calculadas por lotes con `train_classifier`; no se predice en línea todavía)."""
    stmt = select(ClassifierPrediction).order_by(ClassifierPrediction.student_id, ClassifierPrediction.session_id)
    if student_id is not None:
        stmt = stmt.where(ClassifierPrediction.student_id == student_id)
    if modelo_version is not None:
        stmt = stmt.where(ClassifierPrediction.modelo_version == modelo_version)
    elif not todas_las_versiones:
        stmt = stmt.where(ClassifierPrediction.modelo_version == select(func.max(ClassifierPrediction.modelo_version)).scalar_subquery())
    return list(db.scalars(stmt))
