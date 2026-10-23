-- Migración 007: guarda de inyecciones en código (src/app/guarda.py). Idempotente.
--  - `evaluacion_origen` admite 'guarda_inyeccion' (mensaje con patrón de manipulación: valorado 0 sin llamar al LLM);
--  - `guarda_patron` guarda los nombres de los patrones que coincidieron (separados por coma).
-- El CHECK se recrea (DROP IF EXISTS + ADD) ampliando los valores; no cambia ningún dato existente.
ALTER TABLE conversacion_turno ADD COLUMN IF NOT EXISTS guarda_patron TEXT;
ALTER TABLE conversacion_turno DROP CONSTRAINT IF EXISTS conversacion_turno_evaluacion_origen_check;
ALTER TABLE conversacion_turno ADD CONSTRAINT conversacion_turno_evaluacion_origen_check
    CHECK (evaluacion_origen IN ('llm', 'heuristica', 'guarda_inyeccion'));
