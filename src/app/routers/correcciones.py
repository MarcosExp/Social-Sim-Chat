import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CorreccionLog
from app.schemas import CorreccionLogOut
from app.seguridad import exigir_terapeuta

router = APIRouter(prefix="/correcciones", tags=["correcciones"], dependencies=[Depends(exigir_terapeuta)])


@router.get("", response_model=list[CorreccionLogOut])
def historial(session_id: uuid.UUID | None = Query(default=None), conversacion_id: uuid.UUID | None = Query(default=None),
              limite: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)):
    """Historial de correcciones del terapeuta, de la más reciente a la más antigua. `autor` es el nombre declarado
    (cabecera X-Terapeuta), no verificado; de la nota clínica no se guarda el contenido."""
    stmt = select(CorreccionLog).order_by(CorreccionLog.fecha.desc(), CorreccionLog.id.desc()).limit(limite)
    if session_id is not None:
        stmt = stmt.where(CorreccionLog.session_id == session_id)
    if conversacion_id is not None:
        stmt = stmt.where(CorreccionLog.conversacion_id == conversacion_id)
    return list(db.scalars(stmt))
