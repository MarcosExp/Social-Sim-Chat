-- 012 — Se elimina session_data.turnos (JSONB). Acordado con Marcos (23/10/2026) al aceptar el ER v2.
--
-- Motivo: la columna estaba vacía en las 1500 sesiones sintéticas y las sesiones reales guardan sus turnos normalizados en
-- `conversacion_turno` (vista `turn_data`, migración 009). Mantener los dos sitios era una fuente de incoherencias.
-- SEGURIDAD: si alguna fila aún tiene datos en `turnos` (p. ej. un corpus cargado con el generador heredado) la migración
-- ABORTA en lugar de borrarlos; en ese caso exporta esos datos o vacía la columna a propósito y repite. Idempotente.
BEGIN;

DO $$
DECLARE n bigint;
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'session_data' AND column_name = 'turnos') THEN
        EXECUTE 'SELECT count(*) FROM session_data WHERE turnos IS NOT NULL' INTO n;
        IF n > 0 THEN
            RAISE EXCEPTION '012: % fila(s) de session_data tienen datos en "turnos"; no se elimina la columna (exporta o vacía antes)', n;
        END IF;
        ALTER TABLE session_data DROP COLUMN turnos;
    END IF;
END $$;

COMMIT;
