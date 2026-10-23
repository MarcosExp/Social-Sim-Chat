import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, defer
from sqlalchemy.orm.attributes import set_committed_value

from app.db import get_db
from app.seguridad import autor_correccion, exigir_terapeuta
from app.models import CorreccionLog, SessionData, StudentProfileSim
from app.schemas import CorreccionSesionIn, SessionDataOut, SessionDetalleOut

router = APIRouter(prefix="/sessions", tags=["sessions"], dependencies=[Depends(exigir_terapeuta)])


@router.get("", response_model=list[SessionDataOut])
def list_sessions(
    student_id: str | None = Query(default=None),
    origen: str | None = Query(default=None, pattern="^(sintetico|real)$"),
    sin_turnos: bool = Query(default=False, description="Omite el JSON `turnos` (pesa mucho en el corpus heredado)."),
    db: Session = Depends(get_db),
) -> list[SessionData]:
    stmt = select(SessionData).order_by(SessionData.student_id, SessionData.sesion_num)
    if sin_turnos:
        stmt = stmt.options(defer(SessionData.turnos))
    if student_id is not None:
        stmt = stmt.where(SessionData.student_id == student_id)
    if origen is not None:
        stmt = stmt.where(SessionData.origen == origen)
    filas = list(db.scalars(stmt))
    if sin_turnos:
        for f in filas:
            set_committed_value(f, "turnos", None)          # evita una consulta por fila al serializar
    return filas


@router.get("/by-student/{student_id}", response_model=list[SessionDataOut])
def sessions_for_student(student_id: str, db: Session = Depends(get_db)) -> list[SessionData]:
    if db.get(StudentProfileSim, student_id) is None:
        raise HTTPException(status_code=404, detail="student_id no encontrado")
    stmt = (
        select(SessionData)
        .where(SessionData.student_id == student_id)
        .order_by(SessionData.sesion_num)
    )
    return list(db.scalars(stmt))


@router.get("/{session_id}", response_model=SessionDetalleOut)
def detalle(session_id: uuid.UUID, db: Session = Depends(get_db)) -> SessionData:
    """Una sesión con su nota clínica (consola del terapeuta); los listados no la incluyen."""
    fila = db.get(SessionData, session_id)
    if fila is None:
        raise HTTPException(status_code=404, detail="session_id no encontrado")
    return fila


@router.patch("/{session_id}/correccion", response_model=SessionDetalleOut)
def corregir(session_id: uuid.UUID, body: CorreccionSesionIn, db: Session = Depends(get_db),
             autor: str = Depends(autor_correccion)) -> SessionData:
    """El terapeuta corrige la etiqueta de la sesión y/o escribe su nota clínica. Solo cambia lo enviado."""
    fila = db.get(SessionData, session_id)
    if fila is None:
        raise HTTPException(status_code=404, detail="session_id no encontrado")
    if not body.model_fields_set:
        raise HTTPException(status_code=422, detail="Indica etiqueta_corregida y/o nota_clinica.")
    for campo in body.model_fields_set:
        anterior, nuevo = getattr(fila, campo), getattr(body, campo)
        if anterior == nuevo:
            continue
        setattr(fila, campo, nuevo)
        # De la nota clínica (dato sensible) solo se anota que cambió, nunca su contenido.
        con_valor = campo != "nota_clinica"
        db.add(CorreccionLog(autor=autor, tipo="sesion", session_id=session_id, campo=campo,
                             valor_anterior=anterior if con_valor else None, valor_nuevo=nuevo if con_valor else None))
    db.commit()
    db.refresh(fila)
    return fila
