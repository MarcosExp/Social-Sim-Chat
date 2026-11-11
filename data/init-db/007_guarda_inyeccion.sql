-- Migración 007: guarda de inyecciones en código (src/app/guarda.py). Idempotente.
--  - `evaluacion_origen` admite 'guarda_inyeccion' (mensaje con patrón de manipulación: valorado 0 sin llamar al LLM);
--  - `guarda_patron` guarda los nombres de los patrones que coincidieron (separados por coma).
-- El CHECK se recrea (DROP IF EXISTS + ADD) ampliando los valores; no cambia ningún dato existente.
ALTER TABLE conversacion_turno ADD COLUMN IF NOT EXISTS guarda_patron TEXT;
-- Solo se recrea si aún no admite 'guarda_inyeccion': la 013 la amplía y, al reaplicar la 007, no debe volver a estrecharla
-- (fallaría con turnos sintéticos).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'conversacion_turno_evaluacion_origen_check'
                   AND conrelid = 'conversacion_turno'::regclass AND pg_get_constraintdef(oid) LIKE '%guarda_inyeccion%') THEN
        ALTER TABLE conversacion_turno DROP CONSTRAINT IF EXISTS conversacion_turno_evaluacion_origen_check;
        ALTER TABLE conversacion_turno ADD CONSTRAINT conversacion_turno_evaluacion_origen_check
            CHECK (evaluacion_origen IN ('llm', 'heuristica', 'guarda_inyeccion'));
    END IF;
END $$;
