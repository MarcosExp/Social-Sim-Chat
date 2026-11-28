"""Errores de la API en UN solo formato (NF4).

El contrato (docs/api-conversacion.md, `ErrorOut`) promete `{codigo, mensaje, reintentable}`, pero los 422 de validación de FastAPI
llegaban como `{"detail": [...]}` y un fallo de la base de datos o un error no previsto como un «Internal Server Error» de texto
plano: el chat del menor acababa enseñando JSON crudo o «Error 500». Aquí se unifican:

- 422 de validación: conserva `detail` (compatibilidad con el dashboard y los tests) y añade `codigo`, `mensaje` en español y `reintentable`.
- Base de datos no disponible: 503 `bd_no_disponible`, reintentable, con `Retry-After`.
- Cualquier otra excepción: 500 `error_interno`, sin filtrar detalles (se registran en el log del servidor).
"""
import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

log = logging.getLogger("uvicorn.error")


def _una(err: dict) -> str:
    campo = next((str(x) for x in reversed(err.get("loc", ())) if x != "body"), "dato")
    tipo = err.get("type", "")
    ctx = err.get("ctx") or {}
    if tipo == "missing":
        return f"falta «{campo}»"
    if tipo == "string_too_short":
        return f"«{campo}» no puede estar vacío"
    if tipo == "string_too_long":
        return f"«{campo}» es demasiado largo (máximo {ctx.get('max_length', '?')} caracteres)"
    if tipo in ("uuid_parsing", "uuid_type"):
        return f"«{campo}» no es un identificador válido"
    if tipo.startswith("greater_than") or tipo.startswith("less_than"):
        return f"«{campo}» está fuera de rango"
    return f"«{campo}» no es válido ({err.get('msg', 'valor incorrecto')})"


def resumir_errores(errores: list[dict]) -> str:
    """Mensaje corto en español a partir de la lista de errores de Pydantic (máx. 3, para no abrumar)."""
    partes = [_una(e) for e in errores[:3]]
    extra = f" (y {len(errores) - 3} más)" if len(errores) > 3 else ""
    return "Hay datos que no son válidos: " + "; ".join(partes) + extra + "."


def registrar(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validacion(_req: Request, exc: RequestValidationError) -> JSONResponse:
        detalle = jsonable_encoder(exc.errors())
        return JSONResponse(status_code=422, content={"detail": detalle, "codigo": "validacion",
                                                      "mensaje": resumir_errores(detalle), "reintentable": False})

    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    async def _bd(_req: Request, exc: Exception) -> JSONResponse:
        log.error("Base de datos no disponible: %s", exc)
        return JSONResponse(status_code=503, headers={"Retry-After": "5"},
                            content={"codigo": "bd_no_disponible", "reintentable": True,
                                     "mensaje": "No se puede acceder a la base de datos. Inténtalo de nuevo en unos segundos."})

    @app.exception_handler(Exception)
    async def _interno(_req: Request, exc: Exception) -> JSONResponse:
        log.exception("Error no previsto", exc_info=exc)
        return JSONResponse(status_code=500, content={"codigo": "error_interno", "reintentable": False,
                                                      "mensaje": "Algo ha fallado en el servidor."})
