from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import metricas
from app.db import get_db
from app.models import SessionData, StudentProfileSim
from app.schemas import PrediccionRealOut, StudentProfileOut
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
    """¿Se puede predecir el estado de este alumno con sus sesiones REALES? Hoy no, y la respuesta dice por qué.

    No se predice en línea (las predicciones del corpus sintético las calcula `train_classifier` por lotes). El modelo lee
    ventanas de `ventana_requerida` sesiones consecutivas y sus cinco métricas; sobre sesiones reales faltan datos y hay
    métricas provisionales. Los motivos salen de las mismas constantes que usa el cálculo (`metricas.PROVISIONALES*`): cuando
    se resuelvan, `disponible` pasa a verdadero sin tocar este endpoint."""
    from app.ml_config import ventana         # import diferido: arrastra pandas/numpy

    VENTANA = ventana()

    if db.get(StudentProfileSim, student_id) is None:
        raise HTTPException(status_code=404, detail="student_id no encontrado")
    n = {o: db.scalar(select(func.count()).select_from(SessionData).where(
        SessionData.student_id == student_id, SessionData.origen == o)) or 0 for o in ("real", "sintetico")}
    motivos = []
    if n["real"] < VENTANA:
        motivos.append(f"Hacen falta {VENTANA} sesiones reales del alumno para formar una ventana y hay {n['real']}. La ventana debe "
                       "construirse solo con sesiones de origen real: no se pueden mezclar con las sintéticas, aunque la numeración continúe.")
    motivos += [f"{col} real es provisional: {por_que}." for col, por_que in metricas.PROVISIONALES.items()]
    if metricas.PROVISIONALES_EVALUADOR:
        motivos.append("aMLU, PEPE e IRC dependen del evaluador 0/1/2, aún sin validar con conversaciones reales.")
    return PrediccionRealOut(student_id=student_id, disponible=not motivos, ventana_requerida=VENTANA,
                             sesiones_reales=n["real"], sesiones_sinteticas=n["sintetico"], motivos=motivos)
