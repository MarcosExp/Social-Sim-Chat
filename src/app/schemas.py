"""Esquemas Pydantic para la API (entrada/salida)."""
import uuid

from datetime import date, datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StudentProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: str
    competencia_objetivo: str
    trayectoria_disenada: str
    tramo_edad: str | None = None
    n_sesiones: int
    sesion_inicio_evento: int | None = None
    arquetipo: str | None = None
    nivel_ruido: str | None = None
    ambiguo: bool | None = None
    tipo_ambiguo: str | None = None


class SessionDataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    student_id: str
    sesion_num: int
    competencia: str
    origen: str
    fecha: date | None = None
    personaje: str | None = None
    aMLU: float | None = None
    latencia_pragmatica_ms: int | None = None
    IRC_pct: float | None = None
    PEPE: float | None = None
    pct_DET: float | None = None
    pct_DET_observado_en_turnos: float | None = None
    etiqueta_real_disenada: str | None = None
    etiqueta_corregida: str | None = None
    etiqueta_prediccion: str | None = None       # última predicción del clasificador (historial: /predicciones)
    confianza_prediccion: float | None = None
    conversacion_id: uuid.UUID | None = None     # solo origen real
    n_turnos_menor: int | None = None
    n_turnos_evaluados: int | None = None
    n_figuras: int | None = None
    n_turnos_amlu: int | None = None
    lpp_intento1: int | None = None
    lpp_intento2: int | None = None
    definicion_version: str | None = None
    created_at: datetime | None = None
    turnos: list | None = None          # `nota_clinica` NO se expone en los listados (dato sensible)


class SessionDetalleOut(SessionDataOut):
    """Solo en GET/PATCH de una sesión concreta (consola del terapeuta): incluye la nota clínica."""
    nota_clinica: str | None = None


class PrediccionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    student_id: str
    modelo_version: str
    etiqueta_predicha: str
    confianza: float | None = None
    es_estancamiento_operacional: bool = False


class ResumenOut(BaseModel):
    alumnos: int
    sesiones_sinteticas: int
    sesiones_reales: int
    conversaciones: int
    predicciones: int
    versiones_modelo: int
    ultima_version_modelo: str | None = None
    alumnos_por_trayectoria: dict[str, int]
    sesiones_sinteticas_por_etiqueta: dict[str, int]


Etiqueta = Literal["progreso", "estancamiento", "regresion"]


class CorreccionSesionIn(BaseModel):
    """Corrección del terapeuta sobre una sesión. Solo se cambia lo que se envía; `null` borra el valor."""
    etiqueta_corregida: Etiqueta | None = None
    nota_clinica: str | None = Field(None, max_length=2000)


class CorreccionTurnoIn(BaseModel):
    accuracy_corregido: Literal[0, 1, 2] | None = Field(
        ..., description="Valoración corregida (0/1/2) o null para quitar la corrección. El valor original se conserva.")


class FiguraOut(BaseModel):
    """Una fila de la vista `turn_data` del ER (una por figura, no por intento; ADR-002)."""
    model_config = ConfigDict(from_attributes=True)

    turn_id: int
    session_id: uuid.UUID | None = None
    conversacion_id: uuid.UUID
    turno_num: int
    tipo: str
    figura: str
    rama: str | None = None
    accuracy_score: int | None = None
    accuracy_corregido: int | None = None
    accuracy_efectivo: int | None = None
    ayudas_solicitadas: int
    n_intentos: int
    latencia_ms: int | None = None
    latencia_ms_intento2: int | None = None
    iniciativa: bool | None = None
    texto_respuesta: str | None = None
    es_prueba: bool = False
    hubo_respuesta: bool = True                 # campo del ER; el sistema no registra turnos sin respuesta


class HealthOut(BaseModel):
    status: str
    database: str
    auth_terapeuta: str = "desactivada"       # "activa" si hay API_KEY_TERAPEUTA
    llm_provider: str
    llm: str                                   # "ok" o mensaje accionable en español
    llm_model: str | None = None
    llm_modelo_disponible: bool | None = None


# ------------------------------------------------------------------ conversaciones
class ConversacionIn(BaseModel):
    student_id: str
    competencia: str | None = Field(None, description="Si se omite, la competencia objetivo del alumno.")
    alias: str | None = Field(None, max_length=60, description="Nombre que usa el personaje; por defecto student_id.")
    prueba: bool = Field(False, description="Conversación de prueba: no genera sesión real ni métricas.")


class TurnoIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)   # un mensaje en blanco no es un turno (422)
    mensaje: str = Field(..., min_length=1, max_length=500)
    latencia_ms: int | None = Field(None, ge=0, description="Si se omite, se mide en servidor.")


class LLMMeta(BaseModel):
    modelo: str
    prompt_tokens: int | None = None
    eval_tokens: int | None = None
    ollama_ms: int | None = None
    carga_ms: int | None = None
    espera_cola_ms: int
    intentos: int
    ms_total: int


class TurnoBotOut(BaseModel):
    nodo: str
    tipo: str
    personaje: str
    mensajes: list[str]
    texto: str


class ConversacionOut(BaseModel):
    conversacion_id: uuid.UUID
    student_id: str
    competencia: str
    personaje: str
    estado: str
    nodo_actual: str
    intento: int
    guion_version: str
    turno_bot: TurnoBotOut


class TurnoOut(ConversacionOut):
    evaluacion: int | None = None
    evaluacion_origen: str | None = None
    rama: str | None = None
    latencia_ms: int | None = None
    llm: LLMMeta | None = None
    evaluador_version: str | None = None      # prompt+criterio con que se valoró el turno
    guarda_patron: str | None = None          # patrones de inyección detectados (valoración 0 sin LLM)


class TurnoRegistroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    orden: int
    rol: str
    nodo: str
    tipo: str
    intento: int
    texto: str
    evaluacion: int | None = None
    evaluacion_origen: str | None = None
    rama: str | None = None
    latencia_ms: int | None = None
    llm_ms: int | None = None
    evaluador_version: str | None = None
    guarda_patron: str | None = None
    iniciativa: bool | None = None
    accuracy_corregido: int | None = None          # corrección del terapeuta; `evaluacion` conserva el valor original
    ayudas_solicitadas: int = 0
    created_at: datetime | None = None


class ConversacionDetalleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversacion_id: uuid.UUID
    student_id: str
    competencia: str
    personaje: str
    alias: str
    estado: str
    nodo_actual: str
    intento: int
    guion_version: str
    modelo: str | None = None
    es_prueba: bool = False
    turnos: list[TurnoRegistroOut]


class ConversacionResumenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversacion_id: uuid.UUID
    student_id: str
    competencia: str
    personaje: str
    estado: str
    es_prueba: bool = False
    modelo: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CorreccionTurnoOut(BaseModel):
    turno: TurnoRegistroOut
    sesion: SessionDataOut | None = None     # sesión real recalculada (None si la conversación es de prueba)


class ErrorOut(BaseModel):
    codigo: str
    mensaje: str
    reintentable: bool = False


class CorreccionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: datetime
    autor: str                          # declarado por el terapeuta, no verificado
    tipo: str
    conversacion_id: uuid.UUID | None = None
    orden: int | None = None
    session_id: uuid.UUID | None = None
    campo: str
    valor_anterior: str | None = None
    valor_nuevo: str | None = None      # vacío en nota_clinica: no se registra su contenido


class AlumnoChatOut(BaseModel):
    """Lo mínimo que necesita la pantalla del chat del menor (sin trayectoria diseñada ni datos de análisis)."""
    model_config = ConfigDict(from_attributes=True)

    student_id: str
    competencia_objetivo: str


class PrediccionRealOut(BaseModel):
    student_id: str
    disponible: bool
    ventana_requerida: int
    sesiones_reales: int
    sesiones_sinteticas: int
    motivos: list[str]
