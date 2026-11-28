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


# ------------------------------------------------------------------------------------------------ configuración segura
CLAVE_DESARROLLO_CONOCIDA = "dev-terapeuta-local"   # la que traían las versiones anteriores del compose y del README: es pública


class ConfiguracionInsegura(RuntimeError):
    """El backend se niega a arrancar con una configuración que dejaría abiertas las notas clínicas."""


def comprobar_configuracion(entorno: str, clave: str | None) -> list[str]:
    """Valida la clave del terapeuta al arrancar. Devuelve los avisos (desarrollo local) o lanza ConfiguracionInsegura (resto de entornos).

    - Clave vacía: los endpoints del terapeuta (incluida la nota clínica) quedan abiertos.
    - Clave igual a la de desarrollo que publicó el repositorio: cualquiera que lo lea la conoce.
    """
    if not clave:
        problema = "API_KEY_TERAPEUTA está vacía: los endpoints del terapeuta (incluida la nota clínica) quedan abiertos."
    elif clave == CLAVE_DESARROLLO_CONOCIDA:
        problema = "API_KEY_TERAPEUTA es la clave de desarrollo que publica el repositorio."
    else:
        return []
    if entorno != "development":
        raise ConfiguracionInsegura(
            f"{problema} Con ENV={entorno} el backend no arranca así: define una clave propia en environment/.env "
            "(por ejemplo `openssl rand -hex 16`).")
    return [f"{problema} Solo es aceptable en desarrollo local; `make up` genera una clave aleatoria al crear environment/.env."]
