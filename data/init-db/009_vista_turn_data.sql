-- 009 — Vista `turn_data` (ADR-002): contrato del ER entregado en NF2 sobre la tabla de intentos.
--
-- `conversacion_turno` guarda UNA FILA POR INTENTO (máx. 2 por figura: respuesta -> ayuda del guion -> segunda
-- respuesta). El ER del NF2 define `turn_data` con UNA FILA POR TURNO (figura) y accuracy_score 0/1/2. Esta vista
-- agrupa los intentos del menor por (conversacion_id, nodo) con la MISMA regla que usa PEPE
-- (app/metricas.py::puntuar_figuras):
--     2 = acierta a la primera (intento 1 = 2) · 1 = acierta tras la ayuda (intento 2 = 2) · 0 = en otro caso.
-- Solo es lectura: no duplica datos ni cambia `conversacion_turno`. Idempotente.
--
-- Notas de lectura:
--   * accuracy_score     = puntuación de la figura con la valoración ORIGINAL del evaluador.
--   * accuracy_corregido = puntuación de la figura con las correcciones del terapeuta; NULL si ningún intento se corrigió.
--   * accuracy_efectivo  = COALESCE(accuracy_corregido, accuracy_score) (lo que usan las métricas).
--   * iniciativa         = el menor tuvo iniciativa en algún intento de la figura. IRC % de session_data se calcula
--                          sobre INTENTOS (n_turnos_menor), no sobre figuras: no son cifras intercambiables.
--   * texto_respuesta    = texto del último intento (dato sensible en un caso real, RGPD).
--   * `hubo_respuesta` (campo del ER) es siempre TRUE: el sistema no registra turnos sin respuesta del menor (límite conocido).
--   * es_prueba / session_id NULL: conversaciones de prueba o aún abiertas (no tienen sesión); filtrar para análisis.
--   * Cubre las conversaciones que existan, reales o sintéticas (013: una sesión sintética puede tener conversación, siempre con
--     origen = 'sintetico' y es_prueba = true; el origen se lee en conversacion.origen). El generador heredado no crea turnos.
BEGIN;

CREATE OR REPLACE VIEW turn_data AS
WITH menor AS (
    SELECT t.*, COALESCE(t.accuracy_corregido, t.evaluacion) AS ev_efectiva
    FROM conversacion_turno t
    WHERE t.rol = 'menor'
),
figura AS (
    SELECT
        conversacion_id,
        nodo,
        min(id)                                                                          AS turn_id,
        min(orden)                                                                       AS orden_inicio,
        (array_agg(tipo ORDER BY orden))[1]                                              AS tipo,
        (array_agg(rama ORDER BY orden))[1]                                              AS rama,
        count(*)                                                                         AS n_intentos,
        coalesce(sum(ayudas_solicitadas), 0)::int                                        AS ayudas_solicitadas,
        bool_or(coalesce(iniciativa, false))                                             AS iniciativa,
        bool_or(accuracy_corregido IS NOT NULL)                                          AS hay_correccion,
        (array_agg(evaluacion   ORDER BY orden) FILTER (WHERE intento = 1 AND evaluacion   IS NOT NULL))[1] AS o1,
        (array_agg(evaluacion   ORDER BY orden) FILTER (WHERE intento = 2 AND evaluacion   IS NOT NULL))[1] AS o2,
        (array_agg(ev_efectiva  ORDER BY orden) FILTER (WHERE intento = 1 AND ev_efectiva  IS NOT NULL))[1] AS e1,
        (array_agg(ev_efectiva  ORDER BY orden) FILTER (WHERE intento = 2 AND ev_efectiva  IS NOT NULL))[1] AS e2,
        (array_agg(latencia_ms  ORDER BY orden) FILTER (WHERE intento = 1))[1]           AS latencia_ms,
        (array_agg(latencia_ms  ORDER BY orden) FILTER (WHERE intento = 2))[1]           AS latencia_ms_intento2,
        (array_agg(texto        ORDER BY orden DESC))[1]                                 AS texto_respuesta
    FROM menor
    GROUP BY conversacion_id, nodo
),
puntuada AS (
    SELECT f.*,
        (f.tipo = 'competencia' AND (f.o1 IS NOT NULL OR f.o2 IS NOT NULL)) AS evaluada,
        CASE WHEN f.o1 = 2 THEN 2 WHEN f.o2 = 2 THEN 1 ELSE 0 END           AS score_original,
        CASE WHEN f.e1 = 2 THEN 2 WHEN f.e2 = 2 THEN 1 ELSE 0 END           AS score_efectivo
    FROM figura f
)
SELECT
    p.turn_id,
    s.session_id,                                   -- NULL mientras la conversación no ha cerrado su sesión
    p.conversacion_id,
    row_number() OVER (PARTITION BY p.conversacion_id ORDER BY p.orden_inicio)::int AS turno_num,
    p.tipo,
    p.nodo                                          AS figura,
    p.rama,
    CASE WHEN p.evaluada THEN p.score_original END::smallint                         AS accuracy_score,
    CASE WHEN p.evaluada AND p.hay_correccion THEN p.score_efectivo END::smallint    AS accuracy_corregido,
    CASE WHEN p.evaluada THEN p.score_efectivo END::smallint                         AS accuracy_efectivo,
    p.ayudas_solicitadas,
    p.n_intentos,
    p.latencia_ms,
    p.latencia_ms_intento2,
    p.iniciativa,
    p.texto_respuesta,
    c.es_prueba,                                    -- las conversaciones de prueba no generan sesión: filtrar en análisis
    TRUE                                            AS hubo_respuesta   -- campo del ER; ver nota
FROM puntuada p
JOIN conversacion c ON c.conversacion_id = p.conversacion_id
LEFT JOIN session_data s ON s.conversacion_id = p.conversacion_id;

COMMENT ON VIEW turn_data IS 'ADR-002: una fila por figura (turno) del menor, derivada de conversacion_turno (una fila por intento). Regla 2/1/0 = PEPE v2.';

COMMIT;
