-- 013 — Turnos sintéticos (opción A): una sesión sintética puede tener conversación y, con ella, turnos.
--
-- Hasta la 012, `session_data_origen_conversacion_check` exigía (origen = 'real') = (conversacion_id IS NOT NULL): una sesión
-- sintética no podía tener conversación y, por tanto, `turn_data` (vista sobre `conversacion_turno`) no cubría el corpus sintético.
-- Ahora la restricción es «real exige conversación»; el sintético puede tenerla. El generador de turnos (`generar_turnos.py`,
-- de Marcos) crea filas `conversacion` + `conversacion_turno` y enlaza la sesión sintética con `conversacion_id`.
--
-- Cambios:
--   1. `session_data`: real exige `conversacion_id`; sintético puede tenerlo.
--   2. `conversacion.origen` ('real' por defecto | 'sintetico') y CHECK: una conversación sintética es siempre `es_prueba`.
--      Así las métricas reales (`metricas_reales`), los listados y el dashboard, que ya excluyen `es_prueba`, no ven las sintéticas.
--   3. Disparador `session_data_mismo_origen`: una sesión solo se enlaza a una conversación de su mismo origen.
--   4. `conversacion_turno.evaluacion_origen` admite 'sintetico' (valoración fijada por diseño, no por el evaluador).
-- Lo que NO cambia: el entrenamiento solo lee `origen = 'sintetico'` de `session_data` (ANTIFUGA) y la etiqueta de diseño sigue
-- siendo obligatoria en las sintéticas; `turn_data` no cambia (el origen se lee en `conversacion.origen` o `session_data.origen`).
-- Idempotente (se reaplica con `make migrate`; la 007 y la 008 no vuelven a estrechar lo que amplía esta migración).
BEGIN;

ALTER TABLE session_data DROP CONSTRAINT IF EXISTS session_data_origen_conversacion_check;
ALTER TABLE session_data ADD CONSTRAINT session_data_origen_conversacion_check
    CHECK (origen <> 'real' OR conversacion_id IS NOT NULL);

ALTER TABLE conversacion ADD COLUMN IF NOT EXISTS origen TEXT NOT NULL DEFAULT 'real';
ALTER TABLE conversacion DROP CONSTRAINT IF EXISTS conversacion_origen_check;
ALTER TABLE conversacion ADD CONSTRAINT conversacion_origen_check CHECK (origen IN ('real', 'sintetico'));
ALTER TABLE conversacion DROP CONSTRAINT IF EXISTS conversacion_sintetica_es_prueba_check;
ALTER TABLE conversacion ADD CONSTRAINT conversacion_sintetica_es_prueba_check CHECK (origen = 'real' OR es_prueba);

ALTER TABLE conversacion_turno DROP CONSTRAINT IF EXISTS conversacion_turno_evaluacion_origen_check;
ALTER TABLE conversacion_turno ADD CONSTRAINT conversacion_turno_evaluacion_origen_check
    CHECK (evaluacion_origen IN ('llm', 'heuristica', 'guarda_inyeccion', 'sintetico'));

DROP TRIGGER IF EXISTS session_data_sintetico_es_prueba ON session_data;   -- primer borrador de la 013
DROP FUNCTION IF EXISTS session_data_sintetico_es_prueba();

CREATE OR REPLACE FUNCTION session_data_mismo_origen() RETURNS trigger AS $f$
BEGIN
    IF NEW.conversacion_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM conversacion c WHERE c.conversacion_id = NEW.conversacion_id AND c.origen = NEW.origen) THEN
        RAISE EXCEPTION 'la sesion (origen %) enlaza una conversacion de otro origen: una sesion sintetica solo con conversacion sintetica, y una real con una real', NEW.origen
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$f$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS session_data_mismo_origen ON session_data;
CREATE TRIGGER session_data_mismo_origen
    BEFORE INSERT OR UPDATE OF origen, conversacion_id ON session_data
    FOR EACH ROW EXECUTE FUNCTION session_data_mismo_origen();

COMMIT;
