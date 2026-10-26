# ADR-001 — Una única tabla `session_data` con columna `origen`

- **Estado:** aceptada (18/10/2026) · aplicada en el stack (migración `008_er_v2.sql`) y verificada en BD real
- **Decide:** Álvaro García · **Revisa:** Marcos Expósito
- **Afecta a:** ER (`er.mmd` → [`er_v2.mmd`](../er_v2.mmd)), `models.py`, `train_classifier.py`, dashboard, memoria NF3 (apartado arquitectura implementada vs diseñada)

## Contexto
El ER entregado en NF2 tiene **una** tabla de sesiones (`session_data`) con una fila por alumno y sesión, sintética o no. La implementación tenía además `session_real` para las conversaciones reales con el chatbot. Con dos tablas:
1. `classifier_predictions` solo podía apuntar a sesiones sintéticas: **no se podía predecir sobre una sesión real**, que es el objetivo del producto (historia 12 y alerta de estancamiento).
2. El dashboard y los scripts duplicaban consultas y normalizaciones.
3. El ER documentado y el código divergían, algo que la rúbrica penaliza (arquitectura implementada vs diseñada, documentación ↔ repositorio).

## Decisión
Se mantiene **una sola tabla** `session_data`, con `origen IN ('sintetico','real')`:

| Regla | Cómo se garantiza |
|---|---|
| Una sesión real nace de una conversación | `CHECK`: `origen='real'` ⇒ `conversacion_id` no nulo; índice único parcial sobre `conversacion_id` |
| La verdad de diseño solo existe en sintéticas | `CHECK`: `origen='sintetico'` ⇒ `etiqueta_real_disenada` no nula |
| Etiquetas homogéneas | `CHECK` sobre `progreso / estancamiento / regresion` (minúsculas; los acentos solo en pantalla) |
| Numeración por alumno | `UNIQUE (student_id, sesion_num)`; las reales continúan tras las sintéticas |
| **Antifuga** | `train_classifier.py` filtra `WHERE origen='sintetico'`; test automático que falla si entra una real |

`session_real` se elimina tras copiar sus filas (30 en la BD real; migración idempotente).

## Alternativas descartadas
- **A. Mantener `session_real` y hacer `classifier_predictions` polimórfica.** Dos FKs opcionales o una columna `tipo_sesion` sin integridad referencial; más complejidad y ninguna ventaja.
- **C. Vista `UNION` de ambas tablas.** Soluciona la lectura, pero no la integridad de las predicciones.

## Consecuencias
- (+) El ER entregado y el código vuelven a coincidir; el diagrama solo añade `origen`, `conversacion_id` y las columnas de trazabilidad.
- (+) El clasificador puede predecir sobre sesiones reales (pendiente de implementar, historia 12).
- (−) Riesgo de fuga si alguien olvida el filtro de `origen` → mitigado con test y comentario en el código.
- (−) Las columnas de la tabla se renombran a minúsculas (`amlu`, `irc_pct`, `pepe`, `pct_det`). Los atributos Python mantienen `aMLU`, `IRC_pct`, `PEPE`, `pct_DET` para no romper el pipeline de Marcos (`config.yaml`, `features.py`).

## Verificación (BD real, 18/10/2026)
- Copia de seguridad previa (`pg_dump`, con las 30 filas de `session_real`).
- `SELECT origen, count(*) FROM session_data GROUP BY 1` → `sintetico 1500`, `real 30`; `to_regclass('session_real')` → vacío.
- `metricas_reales --recalcular` reproduce los valores previos de las 30 sesiones; `iniciativa` informada en 243 turnos del menor (= suma de `n_turnos_menor`).
- Suite de pruebas: 121 passed (7 nuevas en `test_er_v2.py`); cadena seed → entrenamiento → antifuga correcta (F1-macro 0,793).

## Addendum (18/10/2026) — resultado de la auditoría contra el ER entregado
- **Predicción en `session_data`.** El ER entregado tiene `etiqueta_prediccion` y `confianza_prediccion` en `session_data`; el stack solo las tenía en `classifier_predictions`. Migración **010**: las dos columnas existen y guardan la **última** predicción; `classifier_predictions` se mantiene como **historial por versión de modelo** (el dashboard lo usa). `train_classifier` escribe ambas y pone a NULL la columna de las sintéticas que el nuevo modelo ya no predice (no queda una predicción vieja haciéndose pasar por actual). Backfill con la última versión: 1200 de 1500 sintéticas (las 3 primeras sesiones de cada alumno no tienen predicción: la ventana es de 4).
- **Ventana real.** La numeración real continúa la sintética (`UNIQUE (student_id, sesion_num)`), de modo que una ventana «las últimas 4 sesiones» **mezclaría** orígenes. Toda ventana sobre sesiones reales debe filtrar `origen = 'real'`; `GET /students/{id}/prediccion` ya lo aplica al contar.
- **`turnos` JSONB** se conservaba por fidelidad al ER original, pero estaba vacío en las 1500 sintéticas y no se usaba para las reales (ver ADR-002). **Superado por el addendum del 23/10/2026.**

## Addendum (23/10/2026) — se elimina `session_data.turnos`
Migración **012** (`012_quitar_turnos_jsonb.sql`): se quita la columna `turnos`, a petición de Marcos al revisar el ER v2. Los turnos viven solo en `conversacion_turno` (y en la vista `turn_data`, ADR-002). La migración **aborta** si alguna fila tiene datos en `turnos` (p. ej. un corpus cargado con el generador heredado), en lugar de borrarlos. El ER vigente es [`er_v2.mmd`](../er_v2.mmd) (sin `turnos`, contrastado columna a columna con el esquema real; solo omite las columnas de auditoría `created_at`/`updated_at`). Los recuentos de pruebas de este documento son los de su fecha; el recuento vigente está en el README.

## Addendum (23/10/2026) — turnos sintéticos: opción A (migración 013)
**Decide:** Álvaro (dueño del esquema) · **Revisa:** Marcos, autor de `generar_turnos.py` (borrador en la rama `feature/generar-turnos`).

La regla «`origen='real'` ⇔ `conversacion_id` no nulo» impedía que una sesión sintética tuviera turnos: `turn_data` (ADR-002) es una vista sobre `conversacion_turno` y solo veía conversaciones reales (0 filas con el corpus sembrado). Se relaja a **«real exige `conversacion_id`; sintético puede tenerlo»** (`CHECK (origen <> 'real' OR conversacion_id IS NOT NULL)`). El generador de turnos crea una `conversacion` terminada y sus `conversacion_turno` por cada sesión sintética y enlaza la sesión.

| Riesgo | Cómo se controla |
|---|---|
| Una conversación sintética se contaría como real | `conversacion.origen` (`real` por defecto, `sintetico`) con `CHECK (origen = 'real' OR es_prueba)`: toda conversación sintética es de prueba, y las métricas reales (`metricas_reales`), los listados y el dashboard ya excluyen `es_prueba` |
| Una sesión enlazada a una conversación de otro origen | Disparador `session_data_mismo_origen`: sintética solo con conversación sintética, real solo con real (en inserción y en reenlace) |
| Fuga al entrenamiento | Sin cambios: `train_classifier` filtra `origen='sintetico'`, que ahora puede tener conversación; las reales siguen fuera (test) |
| La valoración sintética parece del evaluador | `conversacion_turno.evaluacion_origen` admite `'sintetico'` (valoración fijada por diseño, no medida) |
| Reaplicar migraciones (`make migrate`) | La 007 y la 008 solo crean sus restricciones si faltan o no admiten lo que amplía la 013; hay un test que reaplica todas con datos sintéticos enlazados |

Alternativa descartada (B): tabla aparte de turnos sintéticos; duplicaría la vista y el código. Es reversible con una migración pequeña.

**Contrato de `generar_turnos.py`:** (1) `conversacion` con `origen='sintetico'`, `es_prueba=true`, `estado='terminada'`; (2) `conversacion_turno` (`orden` correlativo, `rol` `bot`/`menor`, `tipo` `apertura`/`competencia`/`cierre`, `intento` 1 o 2, `evaluacion` 0/1/2 solo en el menor en competencia, `evaluacion_origen='sintetico'`); (3) `session_data.conversacion_id` de la sesión correspondiente. Los turnos se derivan de las métricas de la sesión (`session_data` no se recalcula desde ellos) y el propio generador mide la diferencia recalculando con `app/metricas.py::calcular`; el texto del menor es de relleno (sirve para contar palabras). Esas diferencias y límites se declaran en la memoria.
