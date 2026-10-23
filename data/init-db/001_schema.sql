-- SOCIAL-SIM Chat — esquema inicial de datos
-- (HISTÓRICO: la estructura vigente resulta de aplicar 001→011; ver el ER v2 y los ADR-001/002/003 del NF2 (documentación de la entrega).
--  `turnos` JSONB sigue aquí pero hoy está vacío; la vista `turn_data` es la 009.)
-- Coherente con el ER del NF2 (repo académico MarcosExp/Social-Sim-Chat, NF1/Entregables)
-- y con el formato de salida de generador_corpus_sintetico.py:
--   - `turnos` se mantiene embebido como JSONB en session_data (decisión por
--     defecto del NF2; sigue pendiente de confirmación de Marcos —
--     si en algún momento se normaliza en una tabla
--     `turn_data` aparte, créalo como migración nueva, no reescribiendo esta).

CREATE TABLE IF NOT EXISTS student_profile_sim (
    student_id              TEXT PRIMARY KEY,
    competencia_objetivo    TEXT NOT NULL,
    trayectoria_disenada    TEXT NOT NULL,
    tramo_edad               TEXT NOT NULL,
    n_sesiones               INTEGER NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS session_data (
    session_id                      UUID PRIMARY KEY,
    student_id                      TEXT NOT NULL REFERENCES student_profile_sim(student_id) ON DELETE CASCADE,
    sesion_num                      INTEGER NOT NULL,
    competencia                     TEXT NOT NULL,
    "aMLU"                          NUMERIC(5,2) NOT NULL,
    latencia_pragmatica_ms          INTEGER NOT NULL,
    "IRC_pct"                       NUMERIC(5,1) NOT NULL,
    "PEPE"                          NUMERIC(5,2) NOT NULL,
    "pct_DET"                       NUMERIC(5,1) NOT NULL,
    "pct_DET_observado_en_turnos"   NUMERIC(5,1) NOT NULL,
    etiqueta_real_disenada          TEXT NOT NULL,      -- solo presente en datos sintéticos (ground truth de diseño)
    turnos                          JSONB NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (student_id, sesion_num)
);

CREATE INDEX IF NOT EXISTS idx_session_data_student ON session_data (student_id, sesion_num);

-- Salida del clasificador propio (progreso/estancamiento/regresión),
-- entrenado por separado del LLM — ver NF2_Documentacion_y_Diseno_Tecnico_Grupo12.md §8
-- (repo académico) para los umbrales de éxito propuestos
-- (F1-macro ≥0.75, recall "estancamiento" ≥0.65, precisión ≥0.65).
CREATE TABLE IF NOT EXISTS classifier_predictions (
    id                   BIGSERIAL PRIMARY KEY,
    student_id           TEXT NOT NULL REFERENCES student_profile_sim(student_id) ON DELETE CASCADE,
    session_id           UUID NOT NULL REFERENCES session_data(session_id) ON DELETE CASCADE,
    modelo_version       TEXT NOT NULL,
    etiqueta_predicha     TEXT NOT NULL CHECK (etiqueta_predicha IN ('Progreso', 'Estancamiento', 'Regresión')),
    confianza             NUMERIC(4,3),
    es_estancamiento_operacional BOOLEAN NOT NULL DEFAULT false,  -- criterio de 3 sesiones consecutivas (N=3, M=5, X=60%)
    predicted_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, modelo_version)
);

CREATE INDEX IF NOT EXISTS idx_classifier_predictions_student ON classifier_predictions (student_id, predicted_at);
