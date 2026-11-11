-- Migración 004: métricas por sesión calculadas desde conversaciones REALES (no sintéticas).
-- Tabla aparte de `session_data` a propósito: el corpus sintético tiene etiqueta de diseño y alimenta el
-- entrenamiento; estas sesiones no tienen etiqueta y no deben mezclarse con él. Idempotente.
-- Una fila por conversación terminada (conversacion_id). Definiciones: docs/metricas-reales.md.

-- Las conversaciones de prueba (prueba de humo, demos) no generan sesión real ni ensucian las métricas.
ALTER TABLE conversacion ADD COLUMN IF NOT EXISTS es_prueba BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS session_real (
    conversacion_id                 UUID PRIMARY KEY REFERENCES conversacion(conversacion_id) ON DELETE CASCADE,
    student_id                      TEXT NOT NULL REFERENCES student_profile_sim(student_id) ON DELETE CASCADE,
    sesion_num                      INTEGER NOT NULL,          -- orden entre las sesiones reales del alumno
    competencia                     TEXT NOT NULL,
    "aMLU"                          NUMERIC(5,2),
    latencia_pragmatica_ms          INTEGER,
    "IRC_pct"                       NUMERIC(5,1),
    "PEPE"                          NUMERIC(5,2),
    "pct_DET"                       NUMERIC(5,1),
    "pct_DET_observado_en_turnos"   NUMERIC(5,1),
    n_turnos_menor                  INTEGER NOT NULL,
    n_turnos_evaluados              INTEGER NOT NULL,
    definicion_version              TEXT NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (student_id, sesion_num)
);

CREATE INDEX IF NOT EXISTS idx_session_real_student ON session_real (student_id, sesion_num);
