-- 011 — Historial de correcciones del terapeuta (ADR-003: el dashboard corrige por API).
--
-- Una fila por cambio efectivo: qué se corrigió, valor anterior y nuevo, cuándo y quién. `autor` es el nombre que el terapeuta
-- declara en la cabecera X-Terapeuta: NO está autenticado (la API usa una clave compartida de prototipo).
-- PRIVACIDAD: de la `nota_clinica` (dato sensible, RGPD) solo se registra QUE cambió, nunca su contenido.
-- Idempotente.
BEGIN;

CREATE TABLE IF NOT EXISTS correccion_log (
    id               BIGSERIAL PRIMARY KEY,
    fecha            TIMESTAMPTZ NOT NULL DEFAULT now(),
    autor            TEXT NOT NULL,
    tipo             TEXT NOT NULL CHECK (tipo IN ('turno', 'sesion')),
    conversacion_id  UUID REFERENCES conversacion (conversacion_id) ON DELETE CASCADE,
    orden            INTEGER,
    session_id       UUID REFERENCES session_data (session_id) ON DELETE CASCADE,
    campo            TEXT NOT NULL CHECK (campo IN ('accuracy_corregido', 'etiqueta_corregida', 'nota_clinica')),
    valor_anterior   TEXT,
    valor_nuevo      TEXT,
    CHECK ((tipo = 'turno' AND conversacion_id IS NOT NULL AND orden IS NOT NULL)
        OR (tipo = 'sesion' AND session_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS correccion_log_session_idx ON correccion_log (session_id, fecha DESC);
CREATE INDEX IF NOT EXISTS correccion_log_conversacion_idx ON correccion_log (conversacion_id, fecha DESC);

COMMENT ON TABLE correccion_log IS 'ADR-003: historial de correcciones del terapeuta; autor declarado (no autenticado); sin contenido de la nota clínica.';

COMMIT;
