"""Modelos ORM — coherentes con data/init-db/001..008 (ER v2).

Las tablas ya existen por el script de inicialización de Postgres
(docker-entrypoint-initdb.d); estos modelos son el reflejo en código para
que el backend pueda leer/escribir sin SQL a mano. No se usa
`Base.metadata.create_all()` para evitar divergencias con el SQL versionado.
"""
import uuid

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class StudentProfileSim(Base):
    __tablename__ = "student_profile_sim"

    student_id: Mapped[str] = mapped_column(String, primary_key=True)
    competencia_objetivo: Mapped[str] = mapped_column(String, nullable=False)
    trayectoria_disenada: Mapped[str] = mapped_column(String, nullable=False)
    tramo_edad: Mapped[str | None] = mapped_column(String, nullable=True)
    n_sesiones: Mapped[int] = mapped_column(Integer, nullable=False)
    sesion_inicio_evento: Mapped[int | None] = mapped_column(Integer, nullable=True)   # antes inicio_cambio (migración 008)
    arquetipo: Mapped[str | None] = mapped_column(String, nullable=True)
    nivel_ruido: Mapped[str | None] = mapped_column(String, nullable=True)
    ambiguo: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tipo_ambiguo: Mapped[str | None] = mapped_column(String, nullable=True)

    sesiones: Mapped[list["SessionData"]] = relationship(back_populates="estudiante")


class SessionData(Base):
    """Sesión del ER (migración 008). `origen='sintetico'`: corpus de entrenamiento, con etiqueta de diseño.
    `origen='real'`: conversación terminada (`conversacion_id`), sin etiqueta; NUNCA debe entrar al entrenamiento."""

    __tablename__ = "session_data"
    __table_args__ = (UniqueConstraint("student_id", "sesion_num"),)

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[str] = mapped_column(
        String, ForeignKey("student_profile_sim.student_id", ondelete="CASCADE")
    )
    sesion_num: Mapped[int] = mapped_column(Integer, nullable=False)
    competencia: Mapped[str] = mapped_column(String, nullable=False)
    fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    personaje: Mapped[str | None] = mapped_column(String, nullable=True)
    # Atributos con el nombre de la feature del pipeline (config.yaml); columnas de la BD en minúsculas, como el ER.
    aMLU: Mapped[float | None] = mapped_column("amlu", Numeric(5, 2), nullable=True)
    latencia_pragmatica_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    IRC_pct: Mapped[float | None] = mapped_column("irc_pct", Numeric(5, 1), nullable=True)
    PEPE: Mapped[float | None] = mapped_column("pepe", Numeric(5, 2), nullable=True)
    pct_DET: Mapped[float | None] = mapped_column("pct_det", Numeric(5, 1), nullable=True)
    pct_DET_observado_en_turnos: Mapped[float | None] = mapped_column(
        "pct_det_observado_en_turnos", Numeric(5, 1), nullable=True
    )
    etiqueta_real_disenada: Mapped[str | None] = mapped_column(String, nullable=True)   # solo sintéticas
    etiqueta_corregida: Mapped[str | None] = mapped_column(String, nullable=True)       # corrección del terapeuta
    etiqueta_prediccion: Mapped[str | None] = mapped_column(String, nullable=True)      # última predicción (ER NF2; historial en classifier_predictions)
    confianza_prediccion: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    nota_clinica: Mapped[str | None] = mapped_column(Text, nullable=True)               # sensible (RGPD)
    turnos: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    origen: Mapped[str] = mapped_column(String, nullable=False, default="sintetico", server_default="sintetico")
    conversacion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversacion.conversacion_id", ondelete="CASCADE"), nullable=True)
    n_turnos_menor: Mapped[int | None] = mapped_column(Integer)
    n_turnos_evaluados: Mapped[int | None] = mapped_column(Integer)
    n_figuras: Mapped[int | None] = mapped_column(Integer)
    n_turnos_amlu: Mapped[int | None] = mapped_column(Integer)
    lpp_intento1: Mapped[int | None] = mapped_column(Integer)
    lpp_intento2: Mapped[int | None] = mapped_column(Integer)
    definicion_version: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    estudiante: Mapped["StudentProfileSim"] = relationship(back_populates="sesiones")


class ClassifierPrediction(Base):
    __tablename__ = "classifier_predictions"
    __table_args__ = (
        UniqueConstraint("session_id", "modelo_version"),
        CheckConstraint(
            "etiqueta_predicha IN ('progreso', 'estancamiento', 'regresion')",
            name="classifier_predictions_etiqueta_predicha_check",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        String, ForeignKey("student_profile_sim.student_id", ondelete="CASCADE")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("session_data.session_id", ondelete="CASCADE")
    )
    modelo_version: Mapped[str] = mapped_column(String, nullable=False)
    etiqueta_predicha: Mapped[str] = mapped_column(String, nullable=False)
    confianza: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    es_estancamiento_operacional: Mapped[bool] = mapped_column(Boolean, default=False)


class Conversacion(Base):
    __tablename__ = "conversacion"

    conversacion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    student_id: Mapped[str] = mapped_column(String, ForeignKey("student_profile_sim.student_id", ondelete="CASCADE"))
    competencia: Mapped[str] = mapped_column(String, nullable=False)
    personaje: Mapped[str] = mapped_column(String, nullable=False)
    alias: Mapped[str] = mapped_column(String, nullable=False)
    estado: Mapped[str] = mapped_column(String, nullable=False, default="en_curso")
    nodo_actual: Mapped[str] = mapped_column(String, nullable=False)
    intento: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    guion_version: Mapped[str] = mapped_column(String, nullable=False)
    modelo: Mapped[str | None] = mapped_column(String, nullable=True)
    es_prueba: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    turnos: Mapped[list["ConversacionTurno"]] = relationship(
        back_populates="conversacion", order_by="ConversacionTurno.orden", cascade="all, delete-orphan")


class ConversacionTurno(Base):
    __tablename__ = "conversacion_turno"
    __table_args__ = (UniqueConstraint("conversacion_id", "orden"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversacion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversacion.conversacion_id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    rol: Mapped[str] = mapped_column(String, nullable=False)
    nodo: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    intento: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    evaluacion: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    evaluacion_origen: Mapped[str | None] = mapped_column(String, nullable=True)
    rama: Mapped[str | None] = mapped_column(String, nullable=True)
    latencia_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluador_version: Mapped[str | None] = mapped_column(String, nullable=True)   # migración 006
    guarda_patron: Mapped[str | None] = mapped_column(String, nullable=True)       # migración 007
    iniciativa: Mapped[bool | None] = mapped_column(Boolean, nullable=True)         # migración 008 (alimenta IRC%)
    accuracy_corregido: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)   # corrección del terapeuta
    ayudas_solicitadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversacion: Mapped["Conversacion"] = relationship(back_populates="turnos")


class CorreccionLog(Base):
    """Historial de correcciones del terapeuta (migración 011). `autor` es declarado, no autenticado; de la nota clínica
    solo se registra que cambió, nunca su contenido."""
    __tablename__ = "correccion_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    autor: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str] = mapped_column(String, nullable=False)                 # turno | sesion
    conversacion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversacion.conversacion_id", ondelete="CASCADE"), nullable=True)
    orden: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("session_data.session_id", ondelete="CASCADE"), nullable=True)
    campo: Mapped[str] = mapped_column(String, nullable=False)
    valor_anterior: Mapped[str | None] = mapped_column(String, nullable=True)
    valor_nuevo: Mapped[str | None] = mapped_column(String, nullable=True)
