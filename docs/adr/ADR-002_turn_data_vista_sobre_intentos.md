# ADR-002 — `turn_data` como vista (una fila por figura) sobre `conversacion_turno` (una fila por intento)

- **Estado:** aceptada (18/10/2026) · implementada (migración `009_vista_turn_data.sql`) y aplicada en la BD real del autor
- **Decide:** Álvaro García · **Revisa:** Marcos Expósito
- **Afecta a:** [`er_v2.mmd`](../er_v2.mmd), memoria NF3 (arquitectura implementada vs diseñada), futuras consultas del dashboard

## Contexto
- **NF2 entregado:** `turn_data` con **un evento por turno**; `accuracy_score` 0 / 1 (correcta tras la ayuda) / 2 (correcta a la primera); `accuracy_corregido`; efectivo = `COALESCE(accuracy_corregido, accuracy_score)`.
- **Stack:** `conversacion_turno` con **una fila por intento** (máx. 2 por figura: respuesta → ayuda del guion → segunda respuesta). El detalle por intento alimenta `lpp_intento1/2`, la trazabilidad y las correcciones del terapeuta.
- La regla "2 / 1 / 0 por figura" **ya está en el código** desde la definición v2 del 12/10/2026 (`metricas.puntuar_figuras`, usada por PEPE). Lo que difería del ER era solo la granularidad de almacenamiento.
- `001_schema.sql` y el seguimiento del proyecto dejaban abierto si normalizar `turn_data` en tabla aparte («créala como migración nueva»).

## Decisión
Se conserva `conversacion_turno` tal cual (un intento por fila) y se añade la **vista `turn_data`**, que agrupa los turnos del menor por (`conversacion_id`, `nodo`) y devuelve la forma del ER:

| Columna de la vista | Origen |
|---|---|
| `turn_id`, `turno_num`, `tipo`, `figura`, `rama` | primer intento de la figura (`figura` = `nodo`) |
| `accuracy_score` | 2 si el intento 1 vale 2 · 1 si el intento 2 vale 2 · 0 en otro caso (valoración original) |
| `accuracy_corregido` | misma regla con las correcciones del terapeuta; `NULL` si ningún intento se corrigió |
| `accuracy_efectivo` | `COALESCE(accuracy_corregido, accuracy_score)`: lo que usan las métricas |
| `ayudas_solicitadas`, `n_intentos` | suma / recuento de los intentos |
| `latencia_ms`, `latencia_ms_intento2` | latencia del intento 1 (primera respuesta) y del 2 |
| `iniciativa` | verdadero si hubo iniciativa en algún intento |
| `texto_respuesta` | texto del último intento (sensible en caso real, RGPD) |
| `session_id`, `es_prueba` | enlace a `session_data` (NULL si no hay sesión) y marca de conversación de prueba |

La apertura aparece en la vista, pero sin puntuación (no se evalúa). `hubo_respuesta` no existe: toda fila es una respuesta del menor.

## Alternativas descartadas
- **B. Una fila por turno en la tabla.** Se perdería el texto y la latencia de cada intento; obligaría a reescribir `metricas.py` y a migrar datos reales.
- **C. Solo documentarlo.** Dejaría el ER entregado sin un objeto en BD que lo respalde (rúbrica: documentación ↔ repositorio).

## Consecuencias y límites (para la memoria, con honestidad)
- (+) Cero cambios en datos o en el cálculo de métricas; la vista es de solo lectura y la migración, idempotente.
- (+) El ER entregado y la BD vuelven a coincidir en el nombre y la forma de `turn_data`.
- (−) **IRC % no es intercambiable con la `iniciativa` de la vista**: IRC se calcula sobre intentos (`n_turnos_menor`), la vista agrega por figura.
- (−) **Hoy la vista solo tiene filas de conversaciones reales.** El generador sintético no produce turnos (la columna `session_data.turnos`, vacía en las 1500 sesiones, se eliminó en la migración 012) y el `generar_turnos.py` mencionado en NF2 no está en el repositorio. Desde la migración 013 (ADR-001, addendum del 23/10/2026) una sesión sintética puede tener conversación, así que la vista cubrirá también los turnos sintéticos cuando el generador los cree; pendiente de que Marcos lo entregue.
- (−) La vista incluye conversaciones de prueba o abiertas (`es_prueba`, `session_id` NULL); hay que filtrar en el análisis.

## Verificación
- Suite: **124 passed** (3 pruebas nuevas): una fila por figura y regla 2/1/0; PEPE de la vista = `session_data.pepe`; corrección del terapeuta reflejada.
- **Prueba con datos reales** (copia de seguridad previa a 008 restaurada en un Postgres de pruebas, 008 y 009 aplicadas; 009 dos veces): de las **30 sesiones reales, 30 coinciden** en PEPE y en nº de figuras con `session_data`. La vista devuelve 176 figuras a partir de 243 intentos del menor de esas sesiones; distribución de `accuracy_score`: 0 → 70, 1 → 14, 2 → 31, sin puntuar (aperturas) → 93.

## Addendum (18/10/2026) — correspondencia semántica con el ER, tras la auditoría
- **`evaluacion` (por intento) ≠ `accuracy_score` (por figura).** El guion da ayuda tras un 0 **o un 1** del primer intento, así que `evaluacion = 1` significa «parcial», mientras que `accuracy_score = 1` del ER significa «correcta tras la ayuda». La vista calcula `accuracy_score` con la regla 2 (primer intento 2) / 1 (segundo intento 2) / 0 (resto), la misma que `metricas.puntuar_figuras`.
- **`ayudas_solicitadas`** cuenta las ayudas **ofrecidas por el guion** (intentos > 1), no pedidas por el menor.
- **`hubo_respuesta`** (campo del ER) se añade a la vista como constante `TRUE`: el sistema no guarda turnos sin respuesta del menor. Es un límite conocido, no una medida. `es_prueba` también se expone para poder filtrar.
- La vista cubre las conversaciones que existan; hoy solo las reales. Los turnos sintéticos no existen todavía (`generar_turnos.py`, citado en NF2, no está en los repositorios): pendiente con Marcos. Con la 013 irán con `es_prueba = true` y se distinguen por `session_data.origen` a través de `session_id`.
