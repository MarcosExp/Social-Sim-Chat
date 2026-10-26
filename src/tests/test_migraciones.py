"""`make migrate` reaplica TODAS las migraciones sobre un volumen ya existente: deben ser idempotentes (001 -> 012 en orden)."""
import os
from pathlib import Path

import pytest

# Fuera del contenedor las migraciones están en <repo>/data/init-db; en el contenedor del backend (solo monta src/) las monta
# el compose en MIGRACIONES_DIR.
DIR = Path(os.getenv("MIGRACIONES_DIR") or Path(__file__).resolve().parents[2] / "data" / "init-db")


def test_reaplicar_todas_las_migraciones_no_falla_ni_cambia_el_esquema(bd):
    from sqlalchemy import text

    if not DIR.is_dir():
        pytest.skip(f"no hay migraciones en {DIR} (define MIGRACIONES_DIR)")

    def esquema(c):
        return sorted(tuple(r) for r in c.execute(text(
            "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = current_schema()")))

    ficheros = sorted(DIR.glob("*.sql"))
    assert len(ficheros) >= 12
    with bd.connect() as c:
        antes = esquema(c)
    raw = bd.raw_connection()
    try:
        raw.autocommit = True
        cur = raw.cursor()
        for f in ficheros:
            try:
                cur.execute(f.read_text(encoding="utf-8"))
            except Exception as exc:                                  # noqa: BLE001
                raise AssertionError(f"{f.name} falla al reaplicarse: {exc}") from exc
    finally:
        raw.close()
    with bd.connect() as c:
        assert esquema(c) == antes
