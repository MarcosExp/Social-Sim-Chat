# Métricas por sesión desde turnos reales (c)

Cada conversación **terminada y no de prueba** genera una fila en `session_data` con `origen='real'` (tabla `session_real` de la migración 004, fusionada en la 008; ADR-001), calculada desde
`conversacion_turno` por `src/app/metricas.py`. Las de prueba (`"prueba": true`, usado por `make smoke`) no cuentan.
Conviven con las sintéticas en la misma tabla, pero el corpus sintético tiene etiqueta de diseño y alimenta el
entrenamiento; las reales no tienen etiqueta y **nunca entran en él** (`origen='sintetico'` en el entrenamiento, con test anti-fuga).

## Definiciones (versión `2026-10-12-v3`) — decididas por Álvaro el 2026-10-12
Los documentos del proyecto nombran las cinco métricas pero no fijan la fórmula. Estas son operativas, en las mismas
unidades y rangos que el corpus sintético (`src/generador/config.yaml`). La v2 aplica las 7 decisiones de abajo; la v1 sigue
descrita en el historial de git (`DEFINICION_VERSION` de cada fila indica con cuál se calculó).

| Métrica | Cálculo desde los turnos (v2) | Rango |
|---|---|---|
| **aMLU** | media de palabras por enunciado del menor, **solo turnos de competencia con valoración ≥ 1**; sin ninguno, **NULO** (v3: «sin datos» no es «cero palabras»; las medianas y el informe lo excluyen y muestran la n). Desglose: `n_turnos_amlu` | ~1–7 |
| **Latencia pragmática (LPP)** | mediana de `latencia_ms` de **todos** los turnos del menor, apertura incluida. Desglose (solo competencia): `lpp_intento1`, `lpp_intento2` | ms |
| **IRC %** | % de enunciados del menor con iniciativa: `?`/`¿`, rama `comparte` de la apertura y, **solo en «Preguntas recíprocas», turno de competencia valorado 2** (compartir algo propio) | 0–100 |
| **PEPE** | media de la puntuación **por figura**: 2 si el intento 1 vale 2; 1 si el intento 1 vale 0 o 1 y el intento 2 vale 2; 0 en otro caso | 0–2 |
| **%DET** | **provisional**: % de turnos valorados con 2 (= `pct_DET_observado_en_turnos`) | 0–100 |
| **n_figuras** | nº de figuras (nodos de competencia valorados) de la sesión; se muestra siempre en el informe y el dashboard | — |

### Decisiones del 2026-10-12 (decididas por Álvaro, 2026-10-12)
| # | Regla | Versión | Motivo | Commit |
|---|---|---|---|---|
| 1 | **PEPE por figura**: 2 / 1 (acierta con la ayuda) / 0 | v2 | El TFM puntúa `accuracy_score` por turno con 1 = asistido; el cálculo por intento daba 0 a quien acierta con ayuda | `dbe2ec7` |
| 2 | **%DET provisional**: se mantiene el cálculo, marcado en informe y dashboard, y **fuera del clasificador sobre sesiones reales** (`metricas.columnas_para_clasificador()`) hasta tener varias sesiones por alumno. No se reentrena el clasificador de producción | v2 | El diseño es RQA entre sesiones; el proxy no equivale a la entrada con que se entrenó | `67f945a` |
| 3 | **PEPE «ponderada y acumulada»: aplazado** (solo documentado, sin código) | — | Exige niveles de dificultad que aún no existen | — |
| 4 | **aMLU** solo sobre turnos de competencia con valoración ≥ 1; sin ninguno, **NULO desde la v3** (antes 0); guarda `n_turnos_amlu` | v2 → v3 | Los turnos literales, vacíos o sin sentido inflaban el aMLU (sinsentido 3,67 > literal 2,50) | `fcca49c` |
| 5 | **LPP global**: todos los turnos del menor, apertura incluida; `lpp_intento1` y `lpp_intento2` aparte (migración 005) | v2 | El diseño dice «mediana de latencia global» | `5329f23` |
| 6 | **IRC**: en «Preguntas recíprocas», compartir algo propio (valoración 2 sin `?`) cuenta como iniciativa | v2 | El guion acepta compartir **o** preguntar | `11e6a0a` |
| 7 | **Granularidad**: no se toca la métrica; se muestra siempre `n_figuras` y un aviso de que PEPE y %DET dan saltos de 25-33 puntos | v2 | Con 3-4 figuras por sesión las métricas toman pocos valores | `24a986e` |

**Aviso para Marcos (ML):** la decisión 2 afecta al clasificador. Hasta que haya varias sesiones por alumno, %DET no debe
alimentar la inferencia (a) sobre sesiones reales, y entrenar sin %DET cuesta de media unos 4-5 puntos de recall de
estancamiento (informe de validación §10.4: 0,698 → 0,644 con corpus fijo). **Marcos debe enterarse y confirmar** qué entrada usa
(a) y qué hacer con el umbral 0,65 antes de empezar.

**Evaluador (2026-10-12):** aMLU, PEPE e IRC dependen de la valoración 0/1/2 del LLM y se tratan como **provisionales** (`metricas.PROVISIONALES_EVALUADOR`; marcados en el informe y el dashboard) hasta validar el nuevo prompt. Cada turno valorado guarda `evaluador_version` (prompt+criterio+schema+guarda) y, si salta la guarda de inyecciones, `evaluacion_origen = "guarda_inyeccion"` y `guarda_patron`. Las sesiones anteriores se valoraron con versiones anteriores del prompt (`evaluador_version` NULL o p1). Ver informe de validación §10.6 y §12.

### Casos ambiguos y pendientes
- **PEPE, caso ambiguo (revisar con criterio clínico):** respuesta **parcial (1) en el intento 1 que no acierta tras la ayuda**
  (intento 2 con 0 o 1). La regla la puntúa 0, igual que a quien falla del todo; clínicamente podría merecer 1. Ocurre en 4 de
  las 98 figuras de las 30 sesiones actuales (`sim-011` P2 y P3, `sim-012` D3, `sim-023` P3).
- **PEPE «ponderada y acumulada» (aplazado, decisión 3):** el nombre del diseño implica ponderar por nivel de dificultad y
  acumular en el nivel actual. No hay niveles todavía, así que PEPE es una media simple de una sesión. Pendiente de diseñar
  los niveles; no hay código.
- **%DET:** sigue siendo el % de turnos con 2. PEPE y %DET están casi colineales (0,92 en las reales, 0,94 en el corpus).
- **IRC:** la regla de la decisión 6 depende de la valoración del LLM, que infravalora respuestas que comparten sin preguntar
  («Yo he dibujado un dragón en clase» → 1; informe §10.2), así que rara vez se dispara con el prompt actual.
- **Latencia:** el diseño pide medirla **en el cliente** desde que el mensaje se muestra; el fallback del servidor ya no incluye
  el tiempo del LLM, pero la UI real debe enviar `latencia_ms`. Los valores dependen del cliente real.
- **aMLU** cuenta palabras, no morfemas, y no es «adaptativo»; sigue incluyendo los reintentos válidos.
- Cambiar una definición exige subir `DEFINICION_VERSION` y ejecutar `python -m scripts.metricas_reales --recalcular`.

## Qué comprueba y qué NO comprueba
`python -m scripts.metricas_reales` (o `make metricas`, o la pestaña «Sesiones reales» del dashboard) compara la
distribución real con la del corpus de entrenamiento (p5/mediana/p95 y % de valores fuera de su rango).
Sirve para detectar **desajuste de dominio**: si las métricas reales caen fuera de lo que vio el clasificador, sus
predicciones sobre sesiones reales no son fiables aunque el recall sintético sea bueno.
**No mide el recall real de estancamiento**: no hay etiquetas reales, y una sola conversación guionizada de 3–4
figuras es un dato muy ruidoso. Por eso este paso no resuelve por sí solo la decisión del umbral 0,65 (recall 0,650 → 0,67
entre ejecuciones); lo que sí aporta es saber si merece la pena meter la inferencia (a) en la API.

## Uso
- Automático: al terminar una conversación, la API registra la sesión (si falla, no rompe la conversación; se recupera con
  `make metricas`).
- `make metricas` / `scripts\test-local.ps1 -Metricas`: sincroniza las que falten e imprime la comparación.
- Requiere las migraciones 004 y 005 (`make migrate` o `scripts\setup-local.ps1`; ambas idempotentes).

## Validación local del 2026-10-12 (qwen3:14b; informe completo en `docs/informe-validacion-metricas-reales.md`)
Se generaron 58 conversaciones (28 con el prompt original, ya borradas, y 30 tras corregirlo): 5 perfiles de alumno (respuestas correctas,
correctas tras ayuda, literales, muy cortas, sin sentido/inyección de instrucciones) × 4 competencias, aperturas
afirmativas y negativas, esperas reales de 2-3 s, casos límite (vacío, 500/501 caracteres, turno tras terminar,
alumno/competencia inexistente, conversación abandonada, `prueba:true`). La API, el registro automático en
`session_data` (origen real) y la pestaña del dashboard funcionan; las abandonadas y las de prueba no generan fila.

**Fallos encontrados y corregidos** (commits `91c9709`, `365b8f7`, `e25e12f`):
1. **La valoración 0/1/2 era demasiado indulgente.** Con el prompt original, 21 de 75 respuestas malas (literales, `ok`,
   emojis, «Ignora las instrucciones…») salían con 2, lo que dejaba PEPE y %DET sin validez. Ahora 0-3 de 75 en la batería afinada y
   13/13 buenas, pero con una batería nueva salen 2,3 % de falsos 2 y solo 72 % de buenas con 2 (informe §10.2); mediana de 1,3 s por turno, antes 0,9 s). El criterio clínico sigue pendiente de revisión.
2. **La latencia medida en servidor incluía el tiempo del LLM** (`latencia_ms` = `llm_ms` del turno anterior + ~10 ms,
   unos 1-1,5 s de sesgo sobre un corpus de mediana 4,2 s). Con esperas reales de 2 s y 3 s ahora sale 2008 y 3010 ms.
   Las 28 sesiones generadas con el prompt original se borraron; de las 30 que quedan, 12 (perfiles corto/sinsentido)
   se generaron antes de este arreglo y conservan el sesgo en la latencia.
3. Un mensaje solo de espacios se aceptaba como turno y contaba 0 palabras en el aMLU: ahora 422.

**Valores observados** (30 sesiones posteriores; son perfiles extremos escritos por mí, no niños):
| Métrica | Corpus p5/p50/p95 | Real p5/p50/p95 | Lectura |
|---|---|---|---|
| aMLU | 2,61 / 3,40 / 4,54 | 0,83 / 3,71 / 7,27 | depende de la longitud del texto; no distingue sentido de verborrea |
| Latencia (ms) | 2744 / 4220 / 5180 | 1226 / 2520 / 6807 | simulada por mí o por mis esperas: solo valida el cálculo |
| IRC % | 17,3 / 32,3 / 55,6 | 0 / 0 / 55,5 | 0 salvo en «Preguntas recíprocas» o con `?` |
| PEPE | 0,34 / 0,73 / 1,32 | 0 / 0 / 2,0 | rango completo con 3-4 figuras por sesión |
| %DET | 21,2 / 45,3 / 82,7 | 0 / 0 / 100 | extremos 0/100: pocos turnos y proxy de PEPE |
El informe oficial (rango mín-máx del corpus) da 0-3 % fuera para IRC y %DET aunque la mediana real (0) está bajo el p5 del
corpus; la comparación por p5-p95 es más exigente y marca 63-93 % fuera. Correlación PEPE~%DET: 0,94 en el corpus y 0,92 en
las reales (ya eran casi colineales por diseño).

## Discrepancias detectadas el 2026-10-12 (RESUELTAS por Álvaro el mismo día; ver la tabla de decisiones arriba)
Texto original, conservado como historial. 1 → v2 PEPE por figura; 2 → %DET provisional; 3 → aplazado; 4 → aMLU con valoración ≥ 1; 5 → LPP global + desglose; 6 → IRC; 7 → n_figuras visible.
1. **PEPE y la «ayuda» (0/1/2 por figura).** El TFM define `accuracy_score` por turno: 0 literal, 1 asistido (acierta con ayuda),
   2 correcto. La implementación puntúa por *intento* y PEPE usa solo el primero, así que quien acierta tras la ayuda recibe 0
   (el perfil «asistido» da PEPE 0,0-0,5 y %DET 50-57 %; puntuando por figura sería 1,0-1,25). En 7 de 30 sesiones cambiaría. Además
   el guion usa «asistida» para la respuesta parcial que provoca la ayuda: hay que decidir qué significa un 1.
2. **%DET** es el determinismo RQA sesión a sesión (necesita varias sesiones); hoy es «% de turnos con 2», no lo que consumió
   el clasificador al entrenar. Mientras no se calcule, la entrada %DET real no equivale a la del corpus.
3. **PEPE** («ponderada», «acumulados en el nivel de dificultad actual») es una media simple de una sola sesión.
4. **aMLU** («adaptativo») cuenta palabras, no morfemas, y sin ajuste alguno; incluye reintentos y respuestas sin sentido.
5. **LPP** el diseño dice «mediana de latencia global»; aquí solo turnos de competencia, intentos 1 y 2 mezclados.
6. **IRC**: para «Preguntas recíprocas» el guion acepta compartir algo propio **o** preguntar, pero solo cuenta `?`/`¿` (y la rama
   `comparte` de la apertura); responder compartiendo sin preguntar no suma. Además la apertura casi no ofrece ocasión de iniciativa.
7. Con 3-4 figuras por sesión las métricas toman pocos valores distintos (pasos de 25-33 puntos): la comparación con un corpus
   continuo es sobre todo cualitativa.
