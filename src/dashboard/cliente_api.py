"""Cliente de la API del backend: ÚNICA vía de datos del dashboard (ADR-003).

El dashboard no abre conexiones a Postgres ni lee ficheros del modelo: todo pasa por el contrato REST (/docs).
Así las reglas de negocio (valoración efectiva, recálculo de métricas, qué campos son sensibles) viven en un solo sitio.
"""
import os
from urllib.parse import quote

import httpx
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
API_KEY = os.getenv("API_KEY_TERAPEUTA", "")      # misma clave que el backend; vacía = backend abierto (solo desarrollo local)
_cliente: httpx.Client | None = None


class ErrorAPI(Exception):
    """La API respondió con error o no es alcanzable (el mensaje es apto para mostrarlo al terapeuta)."""


def _c() -> httpx.Client:
    global _cliente
    if _cliente is None:
        _cliente = httpx.Client(base_url=BACKEND_URL, timeout=20, headers={"X-API-Key": API_KEY} if API_KEY else {})
    return _cliente


def _mensaje(r: httpx.Response) -> str:
    try:
        j = r.json()
        d = j.get("detail")
        if isinstance(d, dict):
            d = d.get("mensaje") or d
        return str(j.get("mensaje") or d or j)
    except Exception:  # noqa: BLE001
        return r.text[:200]


def get(path: str, opcional: bool = False, **params):
    """GET JSON. Con `opcional=True`, un 404 devuelve None (p. ej. aún no hay modelo entrenado)."""
    try:
        r = _c().get(path, params={k: v for k, v in params.items() if v is not None})
    except httpx.HTTPError as exc:
        raise ErrorAPI(f"sin respuesta de {BACKEND_URL}: {exc}") from exc
    if r.status_code == 404 and opcional:
        return None
    if r.status_code == 401:
        raise ErrorAPI("la API rechaza la clave del terapeuta: revisa API_KEY_TERAPEUTA en el dashboard y en el backend")
    if r.status_code >= 400:
        raise ErrorAPI(f"{path}: {_mensaje(r)}")
    return r.json()


def patch(path: str, cuerpo: dict, autor: str):
    """PATCH JSON (correcciones del terapeuta) con el nombre declarado de quien corrige (X-Terapeuta). Invalida la caché."""
    try:
        r = _c().patch(path, json=cuerpo, headers={"X-Terapeuta": quote(autor, safe="")})   # cabeceras HTTP = ASCII: nombre codificado
    except httpx.HTTPError as exc:
        raise ErrorAPI(f"sin respuesta de {BACKEND_URL}: {exc}") from exc
    if r.status_code == 401:
        raise ErrorAPI("la API rechaza la clave del terapeuta: revisa API_KEY_TERAPEUTA en el dashboard y en el backend")
    if r.status_code >= 400:
        raise ErrorAPI(_mensaje(r))
    st.cache_data.clear()
    return r.json()


@st.cache_data(ttl=20, show_spinner=False)
def _cacheado(path: str, params: tuple, opcional: bool):
    return get(path, opcional=opcional, **dict(params))


def leer(path: str, opcional: bool = False, **params):
    """GET con caché de 20 s (el dashboard se redibuja en cada interacción)."""
    return _cacheado(path, tuple(sorted(params.items())), opcional)
