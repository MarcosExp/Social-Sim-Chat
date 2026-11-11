-- Migración 003: conversaciones del motor conversacional (endpoint /conversaciones).
-- Guarda el texto íntegro y los eventos por turno (evaluación 0/1/2, latencia del menor, tiempo del LLM).
-- De aquí saldrán después las 5 métricas por sesión (aMLU, latencia, IRC, PEPE, %DET) y el JSONB
-- `session_data.turnos`. Idempotente.

CREATE TABLE IF NOT EXISTS conversacion (
    conversacion_id   UUID PRIMARY KEY,
    student_id        TEXT NOT NULL REFERENCES student_profile_sim(student_id) ON DELETE CASCADE,
    competencia       TEXT NOT NULL,
    personaje         TEXT NOT NULL,
    alias             TEXT NOT NULL,                      -- nombre pseudonimizado que ve el menor
    estado            TEXT NOT NULL DEFAULT 'en_curso' CHECK (estado IN ('en_curso', 'terminada')),
    nodo_actual       TEXT NOT NULL,                      -- nodo del guion al que contestará el menor
    intento           INTEGER NOT NULL DEFAULT 1,         -- 1 = primera respuesta, 2 = tras la ayuda
    guion_version     TEXT NOT NULL,
    modelo            TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conversacion_student ON conversacion (student_id, created_at);

CREATE TABLE IF NOT EXISTS conversacion_turno (
    id                  BIGSERIAL PRIMARY KEY,
    conversacion_id     UUID NOT NULL REFERENCES conversacion(conversacion_id) ON DELETE CASCADE,
    orden               INTEGER NOT NULL,                 -- posición en la conversación (1, 2, 3...)
    rol                 TEXT NOT NULL CHECK (rol IN ('bot', 'menor')),
    nodo                TEXT NOT NULL,
    tipo                TEXT NOT NULL CHECK (tipo IN ('apertura', 'competencia', 'cierre')),
    intento             INTEGER NOT NULL DEFAULT 1,
    texto               TEXT NOT NULL,
    evaluacion          SMALLINT CHECK (evaluacion IN (0, 1, 2)),     -- solo turnos del menor en competencia
    evaluacion_origen   TEXT CHECK (evaluacion_origen IN ('llm', 'heuristica')),
    rama                TEXT,                              -- apertura: afirmativa | negativa | comparte | breve
    latencia_ms         INTEGER,                           -- menor: tiempo que tardó en responder
    llm_ms              INTEGER,                           -- bot: tiempo total de la llamada al LLM
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (conversacion_id, orden)
);
