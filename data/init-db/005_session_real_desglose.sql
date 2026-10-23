-- Migración 005: desglose de las métricas reales (decisiones de Álvaro, 2026-10-12; docs/metricas-reales.md).
-- Solo AÑADE columnas: el significado de las existentes no cambia por esta migración (los cambios de definición los
-- marca `definicion_version`). Idempotente. Las filas anteriores quedan con NULL hasta `scripts.metricas_reales --recalcular`.
ALTER TABLE session_real ADD COLUMN IF NOT EXISTS n_figuras     INTEGER;   -- figuras (nodos de competencia) de la sesión
ALTER TABLE session_real ADD COLUMN IF NOT EXISTS n_turnos_amlu INTEGER;   -- turnos del menor usados en el aMLU
ALTER TABLE session_real ADD COLUMN IF NOT EXISTS lpp_intento1  INTEGER;   -- mediana de latencia, turnos de competencia en intento 1 (ms)
ALTER TABLE session_real ADD COLUMN IF NOT EXISTS lpp_intento2  INTEGER;   -- ídem, intento 2 (tras la ayuda)
