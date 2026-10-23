-- Migración 002: soporta el corpus corregido de Marcos (PR #2).
-- Ese generador no produce turnos de conversación ni tramo de edad, y aporta
-- metadatos de diseño (inicio del cambio, alumnos ambiguos) que sirven para
-- medir el retraso de detección. Idempotente: `make migrate` la aplica sobre
-- un volumen ya existente; en un volumen nuevo la ejecuta Postgres al arrancar.

ALTER TABLE student_profile_sim ALTER COLUMN tramo_edad DROP NOT NULL;
ALTER TABLE student_profile_sim ADD COLUMN IF NOT EXISTS inicio_cambio INTEGER;
ALTER TABLE student_profile_sim ADD COLUMN IF NOT EXISTS ambiguo BOOLEAN;
ALTER TABLE student_profile_sim ADD COLUMN IF NOT EXISTS tipo_ambiguo TEXT;

ALTER TABLE session_data ALTER COLUMN turnos DROP NOT NULL;
ALTER TABLE session_data ALTER COLUMN "pct_DET_observado_en_turnos" DROP NOT NULL;
