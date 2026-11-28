import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.errores import registrar as registrar_errores
from app.llm_client import precalentar_llm
from app.routers import conversaciones, correcciones, health, modelo, predicciones, resumen, sessions, students
from app.seguridad import comprobar_configuracion

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 1. Seguridad: con ENV distinto de «development» no se arranca con la clave vacía o la de desarrollo (lanza antes de servir nada).
    for aviso in comprobar_configuracion(settings.env, settings.api_key_terapeuta):
        log.warning(aviso)
    # 2. Rendimiento: precalienta el modelo en segundo plano (no retrasa el arranque; ver llm_client.precalentar_llm).
    tarea = asyncio.create_task(precalentar_llm()) if settings.llm_precalentar and not settings.llm_simulado else None
    # 3. Clasificador de servicio: se carga `classifier.joblib` si existe (si no, la API funciona y /health lo dice). Nunca lanza.
    from app import prediccion
    log.info("Clasificador de servicio: %s", await asyncio.to_thread(prediccion.estado))
    try:
        yield
    finally:
        if tarea is not None and not tarea.done():
            tarea.cancel()


app = FastAPI(
    lifespan=lifespan,
    title="SOCIAL-SIM Chat API",
    description=(
        "Backend del entrenador conversacional y learning analytics "
        "para menores con TEA/síndrome de Asperger. "
        "Ver /health para comprobar la conexión a Postgres y Ollama."
    ),
    version="0.1.0",
)

registrar_errores(app)

app.include_router(health.router)
app.include_router(students.router)
app.include_router(sessions.router)
app.include_router(conversaciones.router)
app.include_router(predicciones.router)
app.include_router(modelo.router)
app.include_router(resumen.router)
app.include_router(correcciones.router)

# Pantalla del chat del menor (HTML/JS estático sobre la API de conversaciones).
class _ChatSinCache(StaticFiles):
    """El navegador no debe reutilizar un chat.js antiguo: tras cambiar la API (p. ej. X-API-Key) fallaba con la versión en caché."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"      # revalida siempre (ETag): no descarga de nuevo si no cambió
        return resp


app.mount(
    "/chat",
    _ChatSinCache(directory=Path(__file__).parent / "static" / "chat", html=True),
    name="chat",
)


@app.get("/")
def root() -> dict:
    return {"service": "social-sim-chat-backend", "docs": "/docs", "health": "/health", "chat": "/chat/"}
