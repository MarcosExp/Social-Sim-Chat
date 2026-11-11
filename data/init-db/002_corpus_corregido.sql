-- Migración 002: soporta el corpus corregido de Marcos (PR #2).
-- Ese generador no produce turnos de conversación ni tramo de edad, y aporta
-- metadatos de diseño (inicio del cambio, alumnos ambiguos) que sirven para
-- medir el retraso de detección. Idempotente: `make migrate` la aplica sobre
-- un volumen ya existente; en un volumen nuevo la ejecuta Postgres al arrancar.

ALTER TABLE student_profile_sim ALTER COLUMN tramo_edad DROP NOT NULL;
-- `inicio_cambio` se renombra a `sesion_inicio_evento` en la 008: al reaplicar la cadena (make migrate) no se vuelve a crear.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()
                 AND table_name = 'student_profile_sim' AND column_name = 'sesion_inicio_evento') THEN
    ALTER TABLE student_profile_sim ADD COLUMN IF NOT EXISTS inicio_cambio INTEGER;
  END IF;
END $$;
ALTER TABLE student_profile_sim ADD COLUMN IF NOT EXISTS ambiguo BOOLEAN;
ALTER TABLE student_profile_sim ADD COLUMN IF NOT EXISTS tipo_ambiguo TEXT;

-- `turnos` se elimina en la 012: si ya no existe, no hay nada que relajar.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()
             AND table_name = 'session_data' AND column_name = 'turnos') THEN
    ALTER TABLE session_data ALTER COLUMN turnos DROP NOT NULL;
  END IF;
END $$;
-- La 008 renombra esta columna a minúsculas: se busca con cualquiera de los dos nombres.
DO $$
DECLARE c TEXT;
BEGIN
  FOR c IN SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema()
            AND table_name = 'session_data' AND lower(column_name) = 'pct_det_observado_en_turnos' LOOP
    EXECUTE format('ALTER TABLE session_data ALTER COLUMN %I DROP NOT NULL', c);
  END LOOP;
END $$;
