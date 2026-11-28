from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SessionData, StudentProfileSim
from app.schemas import PrediccionRealOut, PrediccionRealSesionOut, StudentProfileOut
from app.seguridad import exigir_terapeuta

router = APIRouter(prefix="/students", tags=["students"], dependencies=[Depends(exigir_terapeuta)])


@router.get("", response_model=list[StudentProfileOut])
def list_students(db: Session = Depends(get_db)) -> list[StudentProfileSim]:
    return list(db.scalars(select(StudentProfileSim).order_by(StudentProfileSim.student_id)))


@router.get("/{student_id}", response_model=StudentProfileOut)
def get_student(student_id: str, db: Session = Depends(get_db)) -> StudentProfileSim:
    student = db.get(StudentProfileSim, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="student_id no encontrado")
    return student


@router.get("/{student_id}/prediccion", response_model=PrediccionRealOut)
def prediccion_sobre_sesiones_reales(student_id: str, db: Session = Depends(get_db)) -> PrediccionRealOut:
    """Predicción ORIENTATIVA del clasificador sobre las sesiones REALES del alumno (modelo de servicio, sin %DET).

    Se calcula con el modelo cargado de `classifier.joblib` (`app/prediccion.py`). Las features son de ventana: hacen falta
    `ventana_requerida` sesiones reales en una misma competencia, y las primeras `ventana_requerida - 1` no tienen predicción.
    `disponible` es falso si no hay modelo o no hay ventana, y `motivos` dice por qué. `avisos` acompaña siempre: el modelo se
    entrenó con datos sintéticos, las escalas reales pueden no coincidir y nada está validado con menores reales."""
    from app import prediccion                # import diferido: arrastra pandas/numpy
    from app.ml_config import ventana

    if db.get(StudentProfileSim, student_id) is None:
        raise HTTPException(status_code=404, detail="student_id no encontrado")
    n_sint = db.scalar(select(func.count()).select_from(SessionData).where(
        SessionData.student_id == student_id, SessionData.origen == "sintetico")) or 0
    r = prediccion.calcular(db, student_id)
    return PrediccionRealOut(
        student_id=student_id, disponible=bool(r.predicciones), modelo_version=r.modelo_version, ventana_requerida=ventana(),
        sesiones_reales=r.sesiones_reales, sesiones_sinteticas=n_sint, motivos=r.motivos, avisos=list(prediccion.AVISOS),
        predicciones=[PrediccionRealSesionOut(**vars(p)) for p in r.predicciones])
