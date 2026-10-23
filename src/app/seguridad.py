"""Autenticación de PROTOTIPO para los endpoints del terapeuta (ADR-003).

- `X-API-Key`: clave compartida (`API_KEY_TERAPEUTA`). No es un sistema de usuarios ni de roles.
- `X-Terapeuta`: nombre que declara quien corrige, codificado en porcentaje (las cabeceras HTTP son ASCII: «Álvaro» viaja como `%C3%81lvaro`). Queda en `correccion_log`, pero NO está verificado.
Un caso real necesitaría autenticar a cada terapeuta (usuarios, caducidad, auditoría fiable) y cifrar la nota clínica.
"""
import secrets
from urllib.parse import unquote

from fastapi import Header, HTTPException

from app.config import settings


def exigir_terapeuta(x_api_key: str | None = Header(default=None)) -> None:
    clave = settings.api_key_terapeuta
    if not clave:                    # autenticación desactivada (desarrollo local)
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, clave):
        raise HTTPException(status_code=401, detail="Falta la clave del terapeuta o es incorrecta (cabecera X-API-Key).")


def autor_correccion(x_terapeuta: str | None = Header(default=None)) -> str:
    autor = unquote(x_terapeuta or "").strip()
    if not autor:
        raise HTTPException(status_code=400, detail="Indica quién corrige (cabecera X-Terapeuta).")
    return autor[:80]
