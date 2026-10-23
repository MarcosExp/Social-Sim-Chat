"""/health — verifica que el backend, Postgres y el motor LLM están conectados.

Este es el primer endpoint a comprobar tras `docker compose up`: si los tres
campos salen en "ok", el entorno de desarrollo está correctamente montado.
El proveedor de LLM (Ollama o tu stack TabbyAPI externo) se reporta también,
para saber contra cuál se está comprobando.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.llm_client import diagnostico_llm
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health(db: Session = Depends(get_db)) -> HealthOut:
    # Postgres
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:  # noqa: BLE001 — queremos reportar cualquier fallo de conexión
        db_status = f"error: {exc}"

    d = await diagnostico_llm()
    llm_status = "ok" if d["estado"] == "ok" else d["detalle"]

    overall = "ok" if db_status == "ok" and llm_status == "ok" else "degraded"
    return HealthOut(
        status=overall,
        database=db_status,
        auth_terapeuta="activa" if settings.api_key_terapeuta else "desactivada",
        llm_provider=settings.llm_provider,
        llm=llm_status,
        llm_model=d.get("modelo"),
        llm_modelo_disponible=d.get("modelo_disponible"),
    )
