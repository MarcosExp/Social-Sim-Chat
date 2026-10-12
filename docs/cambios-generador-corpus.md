# Cambios al generador del corpus sintético (SOCIAL-SIM Chat)

Versión final · 11/10/2026 · incorpora la medición de Marcos sobre su generador real (PR #2).

Objetivo: que el clasificador no pueda acertar por atajos (competencia o nº de sesión) y que las métricas finales sean creíbles (~80-87 % de accuracy, no 100 %). Los valores de este documento están **validados por Marcos sobre su generador real** (PR #2: 10 semillas × validación cruzada por alumno). Una simulación previa mía (`sim_validacion.py`) daba resultados equivalentes.

## 1. Qué entra y qué no entra al modelo

| Campo | Generación | Entrenamiento |
|---|---|---|
| alumno_id | sí | **no** (solo para el split) |
| competencia | sí | **no** |
| perfil / arquetipo | sí | **no** |
| inicio_cambio, ambiguo | sí | **no** |
| nº de sesión | sí | **no** como feature directa |
| aMLU, latencia pragmática, IRC%, PEPE, %DET | sí | sí |
| etiqueta (estancamiento / progreso / regresión) | sí | objetivo |

- Salida en **dos ficheros**: `corpus_train.csv` (alumno_id, sesion, 5 métricas, etiqueta) y `corpus_meta.csv` (alumno_id, competencia, arquetipo, inicio_cambio, ambiguo). Así es imposible usar los metadatos por error.
- Features derivadas con ventana de las **últimas 4 sesiones**, solo con sesiones pasadas (sin mirar hacia delante): para cada métrica, media, pendiente normalizada y diferencia respecto a la media de las 3 primeras sesiones del alumno. Son 15 features (5 métricas × 3). Las sesiones 1-3 no tienen ventana completa y quedan fuera del entrenamiento (1.200 filas de las 1.500).

## 2. Trayectoria y etiqueta por sesión

Se mantiene el diseño de los perfiles A-D (por ejemplo, B: progreso hasta la sesión 7 y estancamiento desde la 8), pero con el inicio del cambio variable:

- **Antes de `inicio_cambio`**: todos los alumnos progresan (pendiente positiva).
- **Desde `inicio_cambio`**: según la trayectoria del alumno. Progreso continúa; estancamiento, pendiente 0; regresión, pendiente negativa (0,8 × la de progreso).
- **Etiqueta por sesión**: `progreso` si la sesión es anterior a `inicio_cambio` o la trayectoria es progreso; en el resto, la etiqueta de la trayectoria. La etiqueta se fija por diseño y **no se recalcula** a partir de la trayectoria ruidosa.

Consecuencia esperada: el modelo falla algo en las sesiones cercanas al inicio del cambio (la ventana de 4 sesiones aún ve el progreso anterior). Es un efecto realista y explica parte de que no llegue al 100 %.

**Decisiones de implementación (Marcos, 11/10, validadas):**

- **`cambio_de_signo`**: a mitad del tramo posterior a `inicio_cambio` (o a mitad de la trayectoria si el alumno progresa) el estancamiento vuelve a progresar, la regresión remonta y el progreso cae. La etiqueta de diseño no cambia: es ambigüedad deliberada. Consecuencia: en un alumno de trayectoria "progreso" con cambio de signo las métricas bajan mientras la etiqueta sigue siendo "progreso", y cualquier alerta ahí cuenta como falsa alerta. La tasa de falsas alertas es, por tanto, algo pesimista.
- **Recaídas**: empeoran las cinco métricas a la vez durante 1-2 sesiones (magnitud 1,5-2,5 σ).
- **`oscilacion_perfil_D` = 1,5**: multiplica el ruido de los alumnos de Deixis.
- El código está en `src/generador/` (generador), `src/ml/features.py` (15 features) y `src/ml/evaluar_corpus.py` (evaluación y comprobaciones antifuga).

## 3. Parámetros del generador (`config.yaml`)

```yaml
seed: 42
n_alumnos: 100            # 25 por competencia
n_sesiones: 15            # 1.500 sesiones en total

inicio_cambio:            # antes era fijo (8 y 10)
  distribucion: uniforme_entera
  min: 4
  max: 12                 # por alumno, independiente de la competencia

pendiente:                # tras inicio_cambio
  progreso:      +1.0     # × pendiente de progreso de cada métrica
  estancamiento:  0.0
  regresion:     -0.8
  variacion_por_alumno: [0.6, 1.4]   # multiplicador aleatorio por alumno

ruido:                    # ¡no usar 0.07! con 0.07 el modelo se queda en ~63 %
  sigma_relativo: 0.02    # 2 % del rango de cada métrica
  ar1_rho: 0.3            # el ruido de una sesión arrastra a la siguiente
  ruido_medicion: 0.02    # ruido independiente adicional

altibajos:                # en TODOS los perfiles
  p_recaida_por_sesion: 0.05
  magnitud_sigma: [1.5, 2.5]
  duracion_sesiones: [1, 2]
  oscilacion_perfil_D: 1.5   # D (deixis) conserva su patrón y lo amplifica

ambiguos:
  proporcion: 0.08        # 8 % de alumnos
  tipos: [inicio_tardio, pendiente_debil, cambio_de_signo]
  # inicio_tardio: inicio_cambio en {11, 12}
  # pendiente_debil: multiplicador 0.3 sobre la pendiente base
  # cambio_de_signo: la tendencia se invierte a mitad de la trayectoria

ruido_etiqueta: 0.02      # 2 % de etiquetas discordantes (desacuerdo entre evaluadores)
```

Pendientes de progreso por sesión usadas en la simulación (referencia): aMLU +0,13; latencia pragmática −170 ms; IRC +2,5 puntos; PEPE +0,07; %DET +4,5 puntos. El ruido se expresa sobre un rango típico por métrica (aMLU 5, latencia 5.000 ms, IRC 100, PEPE 2, %DET 100).

## 4. Emparejamiento competencia → trayectoria como tendencia

Antes: sarcasmo → siempre estancamiento; preguntas recíprocas → siempre regresión. Ahora la trayectoria de cada alumno se muestrea según su competencia:

| Competencia (perfil) | estancamiento | progreso | regresión |
|---|---|---|---|
| Sarcasmo (B) | 0.70 | 0.20 | 0.10 |
| Preguntas recíprocas (C) | 0.20 | 0.10 | 0.70 |
| Metáfora (A) | 0.25 | 0.60 | 0.15 |
| Deixis (D) | 0.30 | 0.55 | 0.15 |

Criterio clínico: la trayectoria esperada pesa 0,55-0,70 y las otras dos se reparten el resto. Sarcasmo y preguntas recíprocas son las de mayor exigencia de Teoría de la Mente y reciprocidad, y concentran estancamiento y regresión. Metáfora y Deixis tienden al progreso; Deixis lleva algo más de estancamiento por su perfil de altibajos.

Distribución resultante (medida por Marcos): **66 % progreso / 19 % estancamiento / 15 % regresión** sobre las 1.500 sesiones; sobre las sesiones 4-15, que son las que entran al modelo, progreso es el 59 % (clase mayoritaria 0,59). Está desbalanceada: usar `class_weight="balanced"` y **F1-macro** como métrica principal, no la accuracy.

**Decisión:** el emparejamiento se adopta como tendencia, no como regla. La competencia marca la dificultad de partida, no el desenlace, y la trayectoria depende también de factores que el sistema no observa (cambios de rutina, ansiedad, comorbilidad). Las probabilidades son supuestos de diseño basados en razonamiento clínico, no tasas empíricas, y la memoria debe declararlo como limitación.

## 5. Esqueleto de generación por alumno

```python
def generar_alumno(i, cfg, rng):
    competencia = COMPETENCIAS[i % 4]
    trayectoria = rng.choice(ETIQUETAS, p=cfg.emparejamiento[competencia])
    inicio = rng.integers(cfg.inicio_cambio.min, cfg.inicio_cambio.max + 1)
    escala = rng.uniform(*cfg.pendiente.variacion_por_alumno)
    ambiguo = rng.random() < cfg.ambiguos.proporcion
    if ambiguo:
        inicio, escala = aplicar_ambiguedad(inicio, escala, rng, cfg)

    nivel = baseline_alumno(i, rng)                         # nivel inicial propio
    filas = []
    for s in range(1, cfg.n_sesiones + 1):
        en_cambio = s >= inicio and trayectoria != "progreso"
        pendiente = cfg.pendiente[trayectoria] if en_cambio else cfg.pendiente.progreso
        nivel += pendiente * escala * PENDIENTE_BASE        # por métrica
        ruido = ar1(rng, cfg.ruido) + rng.normal(0, cfg.ruido.ruido_medicion)
        recaida = recaida_puntual(rng, cfg.altibajos)       # en todos los perfiles
        etiqueta = trayectoria if en_cambio else "progreso"
        etiqueta = etiqueta_con_ruido(etiqueta, rng, cfg.ruido_etiqueta)
        filas.append((metricas(nivel + ruido + recaida), etiqueta))
    return filas, meta(i, competencia, inicio, ambiguo)
```

## 6. Resultados medidos por Marcos (PR #2)

Generador real, RandomForest (300 árboles, `class_weight="balanced"`), validación cruzada por alumno (`StratifiedGroupKFold`, k=5) y 10 semillas del generador (42-51). Media ± desviación entre semillas; entre paréntesis, la desviación entre los 50 folds, que es lo que oscila en una partición suelta.

| Métrica | Modelo real | Heurística (pendiente de PEPE) | Tramposo (competencia + sesión) | Etiquetas permutadas |
|---|---|---|---|---|
| Accuracy | 0,83 ± 0,02 (folds ± 0,04) | 0,75 | 0,61 | 0,45 |
| F1-macro | 0,78 ± 0,02 (folds ± 0,05) | 0,68 | 0,58 | 0,32 |
| Precisión de estancamiento | 0,69 ± 0,05 (folds ± 0,09) | 0,55 | 0,43 | 0,22 |
| Recall de estancamiento | 0,69 ± 0,05 (folds ± 0,10) | 0,45 | 0,56 | 0,18 |

- Clase mayoritaria (sesiones 4-15): 0,59. Sin alumnos ambiguos el modelo real sube a accuracy 0,84 y F1-macro 0,80.
- Por clase (modelo real): progreso, precisión 0,89 y recall 0,91; regresión, precisión 0,78 y recall 0,72.
- **El recall bajo viene de la transición.** En las 2-3 primeras sesiones tras el inicio del cambio el acierto es 0,52, porque la ventana de 4 sesiones aún ve el progreso anterior; a partir de la 3.ª sesión sube a 0,85.
- **Importancia de variables:** las cinco pendientes suman el 62 % (la mayor, la pendiente de %DET, 0,20). El modelo aprende la **evolución**, no el nivel. Ninguna variable domina y la competencia no es feature.

**Detección a nivel de alumno** (alerta = 3 sesiones consecutivas predichas como no-progreso, es decir estancamiento o regresión):

| Medida | Resultado |
|---|---|
| Alumnos con cambio que llegan a alertar | 97 % |
| Retraso mediano desde `inicio_cambio` | 3 sesiones (media 2,8; con la regla de 3 sesiones el mínimo habitual es 2) |
| Alumnos que progresan con alguna falsa alerta | 9 % |

**Barrido de ruido** (`sigma_relativo`, resto de la configuración igual). Es un análisis de sensibilidad, no una validación: muestra cómo cambia la dificultad del problema.

| `sigma_relativo` | F1-macro | Accuracy | Precisión estancamiento | Recall estancamiento |
|---|---|---|---|---|
| 0,01 | 0,82 | 0,86 | 0,76 | 0,75 |
| **0,02 (elegido)** | **0,78** | **0,83** | **0,69** | **0,69** |
| 0,03 | 0,74 | 0,79 | 0,61 | 0,63 |
| 0,05 | 0,66 | 0,73 | 0,51 | 0,51 |
| 0,07 | 0,60 | 0,67 | 0,43 | 0,42 |

Se elige 0,02 como el punto donde el problema es difícil pero resoluble: el corpus original daba 100 % (trivial) y con 0,07 el modelo apenas supera a la heurística. Ojo: con 0,03 el F1-macro (0,74) ya incumple el umbral de 0,75, es decir, umbral y ruido están acoplados. Hay que decirlo así en la memoria.

Matriz de confusión acumulada (10 semillas, 12.000 sesiones evaluadas; filas = real, columnas = predicho):

| Real \ predicho | estancamiento | progreso | regresión |
|---|---|---|---|
| estancamiento | 1.926 | 533 | 302 |
| progreso | 498 | 6.382 | 151 |
| regresión | 368 | 245 | 1.595 |

## 7. Evaluación y comprobaciones antifuga

- **Validación cruzada por alumno** (`StratifiedGroupKFold`, k=5), repetida sobre 10 semillas del generador. Se reporta la media sobre las semillas. Ningún alumno aparece a la vez en train y test.
- Se reportan accuracy, F1, precisión y recall **por clase**, matriz de confusión y la dispersión entre folds.
- **Los umbrales se miran sobre la media de la validación cruzada, no sobre una partición suelta**: entre folds el recall de estancamiento oscila ± 0,10.

Comprobaciones antes de dar por bueno el corpus (resultados medidos por Marcos):

1. **Modelo tramposo** (solo competencia + nº de sesión): su F1-macro debe quedar al menos 0,10 por debajo del modelo real. Resultado: 0,58 frente a 0,78 (0,20 de diferencia; en accuracy, 0,61 frente a 0,83). No puede quedar en el azar: con el emparejamiento como tendencia la competencia lleva información legítima, y las sesiones 1-3 son siempre progreso. Con el generador original daba 100 %.
2. **Etiquetas permutadas**: el criterio es el **F1-macro ≈ 0,33** (azar con tres clases; se acepta ≤ 0,40). Resultado: 0,32, sin fuga. La accuracy no sirve aquí: con `class_weight="balanced"` el modelo no se refugia en "progreso" y cae por debajo de la clase mayoritaria (0,45 frente a 0,59). Corrige el criterio de la versión anterior ("≈ clase mayoritaria"), que solo valía sin pesos de clase.
3. **Importancia de variables**: ninguna feature domina (máximo 0,20) y la competencia no aparece. Cumplido.
4. **Rango esperado**: F1-macro 0,75-0,82 y accuracy 0,80-0,87. Si sale ≥ 0,90, subir `sigma_relativo` (0,02 → 0,03); si sale por debajo de 0,75, bajarlo.

## 8. Umbrales del clasificador (cerrados)

| Umbral | Valor | Medido | Margen |
|---|---|---|---|
| F1-macro | ≥ 0,75 (sin cambios) | 0,78 | +0,03 |
| Precisión de estancamiento | ≥ 0,65 (sin cambios) | 0,69 | +0,04 |
| Recall de estancamiento | **≥ 0,65** (antes ≥ 0,80) | 0,69 | +0,04 |
| Supera a la heurística (F1-macro) | ≥ 0,05 de ventaja | 0,78 frente a 0,68 | +0,10 |

Todos se evalúan sobre la **media de la validación cruzada**. Con ≥ 0,70 el recall incumpliría la mitad de las veces por la dispersión entre particiones.

Valores de referencia a nivel de alumno (alerta de 3 sesiones consecutivas):

| Medida | Valor de referencia | Medido |
|---|---|---|
| Alumnos con cambio detectados | ≥ 90 % | 97 % |
| Retraso mediano de detección | ≤ 4 sesiones | 3 |
| Falsas alertas en alumnos que progresan | ≤ 15 % | 9 % |

**Cómo declararlo en la memoria (con honestidad):**

- El F1-macro ≥ 0,75 y la precisión ≥ 0,65 se fijaron en el borrador de NF2 **antes** de rehacer el generador. El recall se revisó de 0,80 a 0,65 **después de la primera medición**, y la razón es el efecto de la transición, medido y explicado. Hay que decirlo tal cual.
- Los valores de referencia a nivel de alumno se fijaron tras la primera medición, con margen. Se declaran como valores de diseño, no como estándares clínicos.
- La regla de alerta implementada es "3 sesiones consecutivas no-progreso" (estancamiento **o** regresión). El criterio de NF2 hablaba solo de estancamiento: hay que actualizar el texto.
- Todo se mide sobre datos sintéticos: valida el pipeline, no la eficacia clínica.

## 9. Reproducibilidad y documentación

- `seed` y `config.yaml` versionados en el repo; el corpus se regenera con un solo comando.
- Dejar escrito en el README y en la ficha de datos: *corpus sintético; las métricas miden si el modelo aprende los patrones programados por el equipo, no eficacia clínica; los casos ambiguos y el ruido están puestos a propósito.*
- Separar en la memoria lo implementado (generador + clasificador) de las ampliaciones futuras (datos reales con un centro, reentrenamiento con las correcciones del terapeuta).
- El generador solo emite `corpus_train` y `corpus_meta`, que es lo que lee el clasificador. Para sembrar la base de datos y el dashboard (transcripciones, `accuracy_score` por turno) se añade aparte `generar_turnos.py`, que deriva `turn_data` de las métricas de sesión. No es necesario para el clasificador ni para entregar NF2.
- Declarar la limitación: en el corpus las métricas de sesión se generan directamente; en el sistema real se calculan a partir de los turnos con las fórmulas de `metricas-y-etiquetado.md`, que se validan con tests unitarios.
