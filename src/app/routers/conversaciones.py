"""Endpoints de conversación (ver docs/api-conversacion.md)."""
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import conversacion as svc
from app import llm_client, metricas
from app.db import get_db
from app.seguridad import autor_correccion, exigir_terapeuta
from app.models import Conversacion, ConversacionTurno, CorreccionLog, StudentProfileSim
from app.schemas import (AlumnoChatOut, ConversacionDetalleOut, ConversacionIn, ConversacionOut, ConversacionResumenOut,
                         CorreccionTurnoIn, CorreccionTurnoOut, ErrorOut, FiguraOut, LLMMeta, SessionDataOut, TurnoBotOut,
                         TurnoIn, TurnoOut, TurnoRegistroOut)

router = APIRouter(prefix="/conversaciones", tags=["conversaciones"])

_ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut},
        502: {"model": ErrorOut}, 503: {"model": ErrorOut}}


def _error(status: int, codigo: str, mensaje: str, reintentable: bool = False, headers: dict | None = None):
    return JSONResponse(status_code=status, content={"codigo": codigo, "mensaje": mensaje, "reintentable": reintentable},
                        headers=headers)


def _desde_llm(exc: llm_client.LLMError) -> JSONResponse:
    if isinstance(exc, llm_client.RespuestaInvalida):
        status = 502
    elif isinstance(exc, llm_client.ContextoExcedido):
        status = 500
    else:  # LLMNoDisponible, LLMOcupado, ModeloNoEncontrado
        status = 503
    headers = {"Retry-After": "5"} if status == 503 and exc.reintentable else None
    return _error(status, exc.codigo, exc.mensaje, exc.reintentable, headers)


def _bot(t: svc.TurnoBot) -> TurnoBotOut:
    return TurnoBotOut(nodo=t.nodo, tipo=t.tipo, personaje=t.personaje, mensajes=t.mensajes, texto=t.texto)


def _base(r: svc.ResultadoTurno) -> dict:
    c = r.conversacion
    return dict(conversacion_id=c.conversacion_id, student_id=c.student_id, competencia=c.competencia,
                personaje=c.personaje, estado=c.estado, nodo_actual=c.nodo_actual, intento=c.intento,
                guion_version=c.guion_version, turno_bot=_bot(r.turno_bot))


@router.post("", status_code=201, response_model=ConversacionOut, responses=_ERR)
def crear(body: ConversacionIn, db: Session = Depends(get_db)):
    try:
        r = svc.crear_conversacion(db, body.student_id, body.competencia, body.alias, body.prueba)
    except svc.ErrorConversacion as e:
        return _error(e.status, e.codigo, e.mensaje)
    return ConversacionOut(**_base(r))


@router.post("/{conversacion_id}/turnos", response_model=TurnoOut, responses=_ERR)
async def turno(conversacion_id: uuid.UUID, body: TurnoIn, db: Session = Depends(get_db)):
    # Un cerrojo por conversación: dos envíos simultáneos se serializan y el segundo ve el estado ya avanzado.
    async with svc.cerrojo(conversacion_id):
        try:
            conv = svc.cargar(db, conversacion_id)
            db.refresh(conv)
            r = await svc.responder(db, conv, body.mensaje.strip(), body.latencia_ms)
        except svc.ErrorConversacion as e:
            return _error(e.status, e.codigo, e.mensaje)
        except llm_client.LLMError as e:
            db.rollback()
            return _desde_llm(e)
    meta = None
    if r.llm is not None:
        x = r.llm
        meta = LLMMeta(modelo=x.modelo, prompt_tokens=x.prompt_tokens, eval_tokens=x.eval_tokens,
                       ollama_ms=x.ollama_ms, carga_ms=x.carga_ms, espera_cola_ms=x.espera_cola_ms,
                       intentos=x.intentos, ms_total=x.ms_total)
    return TurnoOut(**_base(r), evaluacion=r.evaluacion, evaluacion_origen=r.evaluacion_origen, rama=r.rama,
                    latencia_ms=r.latencia_ms, llm=meta,
                    evaluador_version=r.evaluador_version, guarda_patron=r.guarda_patron)


@router.get("/alumnos", response_model=list[AlumnoChatOut])
def alumnos_para_el_chat(db: Session = Depends(get_db)):
    """Lista mínima para la pantalla del chat (abierta: el menor no tiene clave). No incluye trayectoria ni métricas."""
    return list(db.scalars(select(StudentProfileSim).order_by(StudentProfileSim.student_id)))


@router.get("/{conversacion_id}", response_model=ConversacionDetalleOut, responses=_ERR, dependencies=[Depends(exigir_terapeuta)])
def detalle(conversacion_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        return svc.cargar(db, conversacion_id)
    except svc.ErrorConversacion as e:
        return _error(e.status, e.codigo, e.mensaje)


@router.get("", response_model=list[ConversacionResumenOut], dependencies=[Depends(exigir_terapeuta)])
def listar(student_id: str | None = Query(default=None), estado: str | None = Query(default=None),
           incluir_pruebas: bool = Query(default=False), limite: int = Query(default=200, ge=1, le=1000),
           db: Session = Depends(get_db)):
    """Conversaciones, de la más reciente a la más antigua (por defecto sin las de prueba)."""
    stmt = select(Conversacion).order_by(Conversacion.created_at.desc()).limit(limite)
    if student_id is not None:
        stmt = stmt.where(Conversacion.student_id == student_id)
    if estado is not None:
        stmt = stmt.where(Conversacion.estado == estado)
    if not incluir_pruebas:
        stmt = stmt.where(Conversacion.es_prueba.is_(False))
    return list(db.scalars(stmt))


@router.get("/{conversacion_id}/figuras", response_model=list[FiguraOut], responses=_ERR, dependencies=[Depends(exigir_terapeuta)])
def figuras(conversacion_id: uuid.UUID, db: Session = Depends(get_db)):
    """Contrato `turn_data` del ER: una fila por figura (la vista agrupa los intentos; ADR-002)."""
    try:
        svc.cargar(db, conversacion_id)
    except svc.ErrorConversacion as e:
        return _error(e.status, e.codigo, e.mensaje)
    filas = db.execute(text("SELECT * FROM turn_data WHERE conversacion_id = :c ORDER BY turno_num"),
                       {"c": conversacion_id}).mappings().all()
    return [FiguraOut(**f) for f in filas]


@router.patch("/{conversacion_id}/turnos/{orden}", response_model=CorreccionTurnoOut, responses=_ERR, dependencies=[Depends(exigir_terapeuta)])
def corregir_turno(conversacion_id: uuid.UUID, orden: int, body: CorreccionTurnoIn, db: Session = Depends(get_db),
                   autor: str = Depends(autor_correccion)):
    """El terapeuta corrige la valoración 0/1/2 de un turno del menor. El valor original (`evaluacion`) se conserva;
    las métricas usan COALESCE(accuracy_corregido, evaluacion) y se recalculan en la misma operación."""
    try:
        conv = svc.cargar(db, conversacion_id)
    except svc.ErrorConversacion as e:
        return _error(e.status, e.codigo, e.mensaje)
    if conv.estado != "terminada":
        return _error(409, "conversacion_en_curso", "Solo se corrigen conversaciones terminadas.")
    t = db.scalar(select(ConversacionTurno).where(ConversacionTurno.conversacion_id == conversacion_id,
                                                  ConversacionTurno.orden == orden))
    if t is None:
        return _error(404, "turno_no_encontrado", "No existe ese turno.")
    if t.rol != "menor" or t.evaluacion is None:
        return _error(409, "turno_no_valorable", "Solo se corrigen turnos del menor que tengan valoración.")
    anterior, nuevo = t.accuracy_corregido, body.accuracy_corregido
    t.accuracy_corregido = nuevo
    if anterior != nuevo:
        db.add(CorreccionLog(autor=autor, tipo="turno", conversacion_id=conversacion_id, orden=orden, campo="accuracy_corregido",
                             valor_anterior=None if anterior is None else str(anterior), valor_nuevo=None if nuevo is None else str(nuevo)))
    db.flush()
    sesion = metricas.sesion_de(db, conv.conversacion_id)
    if sesion is not None:
        metricas.recalcular_sesion(db, conv, sesion)       # commit incluido
    else:
        metricas.refrescar_columnas_turno(conv.turnos, conv.competencia)
        db.commit()
    db.refresh(t)
    return CorreccionTurnoOut(turno=TurnoRegistroOut.model_validate(t),
                              sesion=SessionDataOut.model_validate(sesion) if sesion is not None else None)
