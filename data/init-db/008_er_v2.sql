-- Migración 008: alinea el esquema con el ER entregado en NF2 (ER v2). Idempotente (`make migrate` reaplica todos los ficheros).
-- Decisiones (conversación 18/10/2026):
--  * Opción B: UNA sola tabla de sesiones. `session_data` recibe también las sesiones de conversaciones reales
--    (`origen = 'real'`, con `conversacion_id`); `session_real` desaparece tras copiar sus filas. Así el clasificador, las
--    predicciones, la alerta y el dashboard usan una única tabla, como en el ER. El entrenamiento DEBE filtrar
--    `origen = 'sintetico'` (control antifuga; hay un test que lo comprueba).
--  * Las columnas de la BD pasan a minúsculas como en el ER (amlu, irc_pct, pepe, pct_det). Los nombres de las features
--    en Python/pandas no cambian (aMLU, IRC_pct, ...): son los de config.yaml y del pipeline.
--  * Etiquetas en minúsculas y sin tilde (progreso, estancamiento, regresion), como el pipeline; los acentos solo en pantalla.
--  * `inicio_cambio` pasa a `sesion_inicio_evento` (nombre del ER).
--  * Numeración: una sesión real continúa la numeración del alumno (después de sus sesiones sintéticas), porque el ER fija
--    UNIQUE (student_id, sesion_num) y la alerta cuenta sesiones consecutivas del alumno.
BEGIN;

-- ------------------------------------------------------------------ student_profile_sim
ALTER TABLE student_profile_sim ADD COLUMN IF NOT EXISTS arquetipo    TEXT;   -- A / B / C / D (generador)
ALTER TABLE student_profile_sim ADD COLUMN IF NOT EXISTS nivel_ruido  TEXT;   -- bajo / medio / alto
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()
             AND table_name = 'student_profile_sim' AND column_name = 'inicio_cambio') THEN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()
               AND table_name = 'student_profile_sim' AND column_name = 'sesion_inicio_evento') THEN
      -- ya renombrada: una versión anterior de la 002 la volvía a crear al reaplicar la cadena; se funden y se descarta la vieja
      UPDATE student_profile_sim SET sesion_inicio_evento = COALESCE(sesion_inicio_evento, inicio_cambio);
      ALTER TABLE student_profile_sim DROP COLUMN inicio_cambio;
    ELSE
      ALTER TABLE student_profile_sim RENAME COLUMN inicio_cambio TO sesion_inicio_evento;
    END IF;
  END IF;
END $$;
UPDATE student_profile_sim
   SET trayectoria_disenada = translate(lower(split_part(trayectoria_disenada, ' (', 1)), 'ó', 'o')
 WHERE trayectoria_disenada <> translate(lower(split_part(trayectoria_disenada, ' (', 1)), 'ó', 'o');

-- ------------------------------------------------------------------ session_data: nombres en minúsculas
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT * FROM (VALUES ('aMLU', 'amlu'), ('IRC_pct', 'irc_pct'), ('PEPE', 'pepe'), ('pct_DET', 'pct_det'),
                                 ('pct_DET_observado_en_turnos', 'pct_det_observado_en_turnos')) AS v(viejo, nuevo)
  LOOP
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()
               AND table_name = 'session_data' AND column_name = r.viejo) THEN
      EXECUTE format('ALTER TABLE session_data RENAME COLUMN %I TO %I', r.viejo, r.nuevo);
    END IF;
  END LOOP;
END $$;

-- ------------------------------------------------------------------ session_data: columnas del ER y de las sesiones reales
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS fecha                DATE;
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS personaje            TEXT;
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS etiqueta_corregida   TEXT;   -- corrección del terapeuta
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS nota_clinica         TEXT;   -- sensible en un caso real (RGPD)
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS origen               TEXT NOT NULL DEFAULT 'sintetico';
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS conversacion_id      UUID REFERENCES conversacion(conversacion_id) ON DELETE CASCADE;
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS n_turnos_menor       INTEGER;
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS n_turnos_evaluados   INTEGER;
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS n_figuras            INTEGER;
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS n_turnos_amlu        INTEGER;
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS lpp_intento1         INTEGER;
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS lpp_intento2         INTEGER;
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS definicion_version   TEXT;

-- Una sesión real puede tener métricas nulas (p. ej. aMLU sin turnos válidos) y no tiene etiqueta de diseño.
ALTER TABLE session_data ALTER COLUMN amlu                    DROP NOT NULL;
ALTER TABLE session_data ALTER COLUMN latencia_pragmatica_ms  DROP NOT NULL;
ALTER TABLE session_data ALTER COLUMN irc_pct                 DROP NOT NULL;
ALTER TABLE session_data ALTER COLUMN pepe                    DROP NOT NULL;
ALTER TABLE session_data ALTER COLUMN pct_det                 DROP NOT NULL;
ALTER TABLE session_data ALTER COLUMN etiqueta_real_disenada  DROP NOT NULL;

UPDATE session_data
   SET etiqueta_real_disenada = translate(lower(split_part(etiqueta_real_disenada, ' (', 1)), 'ó', 'o')
 WHERE etiqueta_real_disenada IS NOT NULL
   AND etiqueta_real_disenada <> translate(lower(split_part(etiqueta_real_disenada, ' (', 1)), 'ó', 'o');

ALTER TABLE session_data DROP CONSTRAINT IF EXISTS session_data_origen_check;
ALTER TABLE session_data ADD CONSTRAINT session_data_origen_check CHECK (origen IN ('sintetico', 'real'));
ALTER TABLE session_data DROP CONSTRAINT IF EXISTS session_data_origen_conversacion_check;
ALTER TABLE session_data ADD CONSTRAINT session_data_origen_conversacion_check
    CHECK ((origen = 'real') = (conversacion_id IS NOT NULL));
ALTER TABLE session_data DROP CONSTRAINT IF EXISTS session_data_etiqueta_diseno_check;
ALTER TABLE session_data ADD CONSTRAINT session_data_etiqueta_diseno_check
    CHECK (origen = 'real' OR etiqueta_real_disenada IS NOT NULL);
ALTER TABLE session_data DROP CONSTRAINT IF EXISTS session_data_etiquetas_validas_check;
ALTER TABLE session_data ADD CONSTRAINT session_data_etiquetas_validas_check
    CHECK ((etiqueta_real_disenada IS NULL OR etiqueta_real_disenada IN ('progreso', 'estancamiento', 'regresion'))
       AND (etiqueta_corregida     IS NULL OR etiqueta_corregida     IN ('progreso', 'estancamiento', 'regresion')));
CREATE UNIQUE INDEX IF NOT EXISTS idx_session_data_conversacion ON session_data (conversacion_id) WHERE conversacion_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_session_data_origen ON session_data (origen, student_id, sesion_num);

-- ------------------------------------------------------------------ session_real -> session_data (origen = 'real')
DO $$
BEGIN
  IF to_regclass('session_real') IS NOT NULL THEN
    INSERT INTO session_data (session_id, student_id, sesion_num, competencia, personaje, fecha,
                              amlu, latencia_pragmatica_ms, irc_pct, pepe, pct_det, pct_det_observado_en_turnos,
                              etiqueta_real_disenada, origen, conversacion_id,
                              n_turnos_menor, n_turnos_evaluados, n_figuras, n_turnos_amlu, lpp_intento1, lpp_intento2,
                              definicion_version, created_at)
    SELECT gen_random_uuid(), r.student_id,
           r.sesion_num + COALESCE((SELECT max(s.sesion_num) FROM session_data s
                                     WHERE s.student_id = r.student_id AND s.origen = 'sintetico'), 0),
           r.competencia, c.personaje, r.created_at::date,
           r."aMLU", r.latencia_pragmatica_ms, r."IRC_pct", r."PEPE", r."pct_DET", r."pct_DET_observado_en_turnos",
           NULL, 'real', r.conversacion_id,
           r.n_turnos_menor, r.n_turnos_evaluados, r.n_figuras, r.n_turnos_amlu, r.lpp_intento1, r.lpp_intento2,
           r.definicion_version, r.created_at
      FROM session_real r JOIN conversacion c USING (conversacion_id)
     WHERE NOT EXISTS (SELECT 1 FROM session_data x WHERE x.conversacion_id = r.conversacion_id);
    DROP TABLE session_real;   -- ya copiada; 004/005 la recrean vacía si se reaplican y esta migración la vuelve a retirar
  END IF;
END $$;

-- ------------------------------------------------------------------ conversacion_turno: campos del ER
ALTER TABLE conversacion_turno ADD COLUMN IF NOT EXISTS iniciativa          BOOLEAN;   -- el menor pregunta o aporta algo propio (alimenta IRC%)
ALTER TABLE conversacion_turno ADD COLUMN IF NOT EXISTS accuracy_corregido  SMALLINT;  -- corrección del terapeuta; las métricas usan COALESCE(corregido, evaluacion)
ALTER TABLE conversacion_turno ADD COLUMN IF NOT EXISTS ayudas_solicitadas  INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conversacion_turno DROP CONSTRAINT IF EXISTS conversacion_turno_accuracy_corregido_check;
ALTER TABLE conversacion_turno ADD CONSTRAINT conversacion_turno_accuracy_corregido_check
    CHECK (accuracy_corregido IS NULL OR accuracy_corregido IN (0, 1, 2));
UPDATE conversacion_turno SET ayudas_solicitadas = 1
 WHERE rol = 'menor' AND tipo = 'competencia' AND intento > 1 AND ayudas_solicitadas = 0;
-- `iniciativa` de los turnos anteriores queda NULL hasta `python -m scripts.metricas_reales --recalcular`.

-- ------------------------------------------------------------------ classifier_predictions: etiquetas en minúsculas
ALTER TABLE classifier_predictions DROP CONSTRAINT IF EXISTS classifier_predictions_etiqueta_predicha_check;
UPDATE classifier_predictions
   SET etiqueta_predicha = translate(lower(etiqueta_predicha), 'ó', 'o')
 WHERE etiqueta_predicha <> translate(lower(etiqueta_predicha), 'ó', 'o');
ALTER TABLE classifier_predictions ADD CONSTRAINT classifier_predictions_etiqueta_predicha_check
    CHECK (etiqueta_predicha IN ('progreso', 'estancamiento', 'regresion'));

COMMIT;
