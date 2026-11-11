-- Migración 006: con qué evaluador se valoró cada turno (prompt + criterio + schema; ver `evaluador_version()` en
-- src/app/conversacion.py). Solo AÑADE una columna; idempotente. Los turnos anteriores quedan con NULL = evaluador
-- desconocido (valorados antes de existir este registro, con versiones anteriores del prompt).
ALTER TABLE conversacion_turno ADD COLUMN IF NOT EXISTS evaluador_version TEXT;
