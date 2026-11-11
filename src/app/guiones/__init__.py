"""Carga y validación de los guiones de diálogo (app/guiones/guiones.json).

Los guiones son DATOS, no código: el equipo pedagógico edita el JSON y los tests
comprueban que la estructura sigue siendo válida (ids únicos, campos obligatorios).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

RUTA = Path(__file__).with_name("guiones.json")
CLAVES_APERTURA = {"a1", "a2", "rama_2A", "rama_2B", "a3", "rama_3A", "rama_3B", "cierre"}


@dataclass(frozen=True)
class Turno:
    id: str
    frase: str
    ayuda: str
    correcta: str
    contexto: str | None = None

    @property
    def texto(self) -> str:
        """Lo que dice el personaje: contexto escénico (si hay) + frase."""
        return f"({self.contexto}) {self.frase}" if self.contexto else self.frase


@dataclass(frozen=True)
class Guion:
    competencia: str
    personaje: str
    objetivo: str
    turnos: tuple[Turno, ...]
    cierre: str


@dataclass(frozen=True)
class Guiones:
    version: str
    personajes: dict
    apertura: dict
    competencias: dict[str, Guion]


class GuionInvalido(ValueError):
    pass


def validar(data: dict) -> Guiones:
    falta = CLAVES_APERTURA - set(data.get("apertura", {}))
    if falta:
        raise GuionInvalido(f"Faltan claves de apertura: {sorted(falta)}")
    ids: set[str] = set()
    comps: dict[str, Guion] = {}
    for nombre, g in data.get("competencias", {}).items():
        if g["personaje"] not in data["personajes"]:
            raise GuionInvalido(f"{nombre}: personaje desconocido {g['personaje']!r}")
        turnos = []
        for t in g["turnos"]:
            for campo in ("id", "frase", "ayuda", "correcta"):
                if not t.get(campo):
                    raise GuionInvalido(f"{nombre}: turno sin '{campo}': {t}")
            if t["id"] in ids:
                raise GuionInvalido(f"id de turno repetido: {t['id']}")
            ids.add(t["id"])
            turnos.append(Turno(t["id"], t["frase"], t["ayuda"], t["correcta"], t.get("contexto")))
        if not turnos or not g.get("cierre"):
            raise GuionInvalido(f"{nombre}: sin turnos o sin cierre")
        comps[nombre] = Guion(nombre, g["personaje"], g.get("objetivo", ""), tuple(turnos), g["cierre"])
    if not comps:
        raise GuionInvalido("No hay competencias")
    return Guiones(data["version"], data["personajes"], data["apertura"], comps)


@lru_cache(maxsize=1)
def cargar_guiones() -> Guiones:
    return validar(json.loads(RUTA.read_text(encoding="utf-8")))
