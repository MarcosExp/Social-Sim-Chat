-- 010 — `etiqueta_prediccion` y `confianza_prediccion` en session_data (ER entregado en NF2).
--
-- El ER del NF2 guarda la predicción del clasificador en `session_data`. La implementación guarda el HISTORIAL por versión de
-- modelo en `classifier_predictions` (varias predicciones por sesión; ver ADR-001). Para que el esquema real cumpla el ER
-- entregado, `session_data` conserva además la ÚLTIMA predicción (desnormalizada): la escribe `train_classifier` en la misma
-- transacción que el historial. Idempotente.
BEGIN;

ALTER TABLE session_data ADD COLUMN IF NOT EXISTS etiqueta_prediccion  TEXT;
ALTER TABLE session_data ADD COLUMN IF NOT EXISTS confianza_prediccion NUMERIC(4, 3);

ALTER TABLE session_data DROP CONSTRAINT IF EXISTS session_data_etiqueta_prediccion_check;
ALTER TABLE session_data ADD CONSTRAINT session_data_etiqueta_prediccion_check
    CHECK (etiqueta_prediccion IS NULL OR etiqueta_prediccion IN ('progreso', 'estancamiento', 'regresion'));

-- Relleno desde el historial: última versión del modelo (las versiones llevan marca de tiempo y ordenan alfabéticamente).
UPDATE session_data s
   SET etiqueta_prediccion = p.etiqueta_predicha, confianza_prediccion = p.confianza
  FROM classifier_predictions p
 WHERE p.session_id = s.session_id
   AND p.modelo_version = (SELECT max(modelo_version) FROM classifier_predictions);

COMMIT;
