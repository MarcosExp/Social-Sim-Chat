"""`make migrate` reaplica TODAS las migraciones sobre un volumen ya existente: deben ser idempotentes (001 -> 013 en orden),
también con datos que solo la 013 permite (sesión sintética enlazada a una conversación)."""
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "data" / "init-db"


def test_reaplicar_todas_las_migraciones_no_falla_ni_cambia_el_esquema(bd, alumno):
    from sqlalchemy import text

    from tests.test_er_v2 import sintetica_con_turnos

    def esquema(c):
        return sorted(tuple(r) for r in c.execute(text(
            "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = current_schema()")))

    ficheros = sorted(DIR.glob("*.sql"))
    assert len(ficheros) >= 13
    sintetica_con_turnos(bd, alumno)          # la 008 no debe volver a endurecer la restricción y fallar con esta fila
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
