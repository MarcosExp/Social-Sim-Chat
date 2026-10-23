-- 013 — Turnos sintéticos (opción A): una sesión sintética puede tener conversación y, con ella, turnos.
--
-- Hasta la 012, `session_data_origen_conversacion_check` exigía (origen = 'real') = (conversacion_id IS NOT NULL): una sesión
-- sintética no podía tener conversación y, por tanto, `turn_data` (vista sobre `conversacion_turno`) no cubría el corpus sintético.
-- Ahora la restricción es «real exige conversación»; el sintético puede tenerla. El generador de turnos (`generar_turnos.py`,
-- a cargo de Marcos) crea filas `conversacion` + `conversacion_turno` y enlaza la sesión sintética con `conversacion_id`.
--
-- Lo que NO cambia:
--   * El entrenamiento sigue leyendo solo `origen = 'sintetico'` (ANTIFUGA); la etiqueta de diseño sigue siendo obligatoria en sintéticas.
--   * Las métricas y listados reales ya excluyen `conversacion.es_prueba`, así que las conversaciones sintéticas DEBEN ir con
--     `es_prueba = true`. Como un CHECK no puede mirar otra tabla, lo garantiza el disparador `session_data_sintetico_es_prueba`:
--     rechaza una sesión sintética enlazada a una conversación que no sea de prueba.
--   * `turn_data` no cambia: ya hace LEFT JOIN con `session_data` por `conversacion_id`; el origen de una fila se lee en
--     `session_data.origen` a través de `session_id`.
-- Idempotente (se reaplica con `make migrate`; la 008 solo crea la restricción si falta).
BEGIN;

ALTER TABLE session_data DROP CONSTRAINT IF EXISTS session_data_origen_conversacion_check;
ALTER TABLE session_data ADD CONSTRAINT session_data_origen_conversacion_check
    CHECK (origen <> 'real' OR conversacion_id IS NOT NULL);

CREATE OR REPLACE FUNCTION session_data_sintetico_es_prueba() RETURNS trigger AS $f$
BEGIN
    IF NEW.origen = 'sintetico' AND NEW.conversacion_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM conversacion c WHERE c.conversacion_id = NEW.conversacion_id AND c.es_prueba) THEN
        RAISE EXCEPTION 'sesion sintetica enlazada a una conversacion que no es de prueba (es_prueba = true): entraria en las metricas reales'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$f$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS session_data_sintetico_es_prueba ON session_data;
CREATE TRIGGER session_data_sintetico_es_prueba
    BEFORE INSERT OR UPDATE OF origen, conversacion_id ON session_data
    FOR EACH ROW EXECUTE FUNCTION session_data_sintetico_es_prueba();

COMMIT;
