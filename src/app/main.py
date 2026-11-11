from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import conversaciones, correcciones, health, modelo, predicciones, resumen, sessions, students

app = FastAPI(
    title="SOCIAL-SIM Chat API",
    description=(
        "Backend del entrenador conversacional y learning analytics "
        "para menores con TEA/síndrome de Asperger. "
        "Ver /health para comprobar la conexión a Postgres y Ollama."
    ),
    version="0.1.0",
)

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
