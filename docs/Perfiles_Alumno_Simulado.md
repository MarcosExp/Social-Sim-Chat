# Perfiles de alumno simulado — SOCIAL-SIM Chat

**Tarea de reparto:** Álvaro García Puche — "Especificación de los perfiles de alumno simulado y sus trayectorias"
**Base teórica:** TFM 2020 (García Puche) — grupos de edad 6-8 / 8-10 / 10-12 años, cuatro competencias pragmáticas de referencia (metáfora, sarcasmo, deixis, preguntas recíprocas), y las cuatro áreas de dificultad del TEA/SA (interacción social, comunicación, intereses restringidos, rutinas/inflexibilidad).

Cada perfil define una **trayectoria de evolución conocida por diseño** (para poder evaluar el clasificador contra una verdad conocida) más un rango de variabilidad realista alrededor de esa trayectoria, para que las cinco métricas no sean una función trivial de una sola variable.

**Actualización (revisión con corpus de referencias unificado):** se detectó que el Perfil B (Sarcasmo, 9 años/tramo 8-10) estaba emparejado en `Guiones_Dialogo.md` con el personaje "Teo" (pensado para 10-12 años). Se corrige incorporando un personaje propio para el tramo 8-10 ("Nico") en ese documento, sin cambios en este perfil. Las notas clínicas de los perfiles B y C se refuerzan además con citas concretas del corpus.

> **Nota v2 (12/10/2026) — alineación con el generador de corpus (PR #2, `config.yaml`).** Los cuatro perfiles de este documento pasan a ser **arquetipos de competencia**, no alumnos individuales con trayectoria fija:
> - El generador produce **25 alumnos por competencia (100 en total; el arquetipo solo fija la competencia, un perfil B puede progresar) × 15 sesiones**; en este documento los campos de sesiones (14/15/16) y las sesiones de cambio fijas (p. ej. 8 y 10) son solo ejemplos.
> - La **trayectoria** (progreso / estancamiento / regresión) se **sortea por alumno según su competencia**, como tendencia y no como regla: Sarcasmo 0,70 / 0,20 / 0,10; Preguntas recíprocas 0,20 / 0,10 / 0,70; Metáfora 0,25 / 0,60 / 0,15; Deixis 0,30 / 0,55 / 0,15 (estancamiento / progreso / regresión). La trayectoria que figura en cada perfil es la más probable de su competencia.
> - El **inicio del cambio** se sortea entre las sesiones 4 y 12 (antes, todos progresan).
> - Los **rangos de métricas** son orientativos; los tests deben comprobar que una métrica cae dentro del rango documentado para esa métrica, no que un alumno concreto siga el perfil.
> - Son supuestos de diseño basados en razonamiento clínico, no tasas empíricas. Detalle en NF2, sección 8.

---

## Cómo se usa este documento

- `student_id`: identificador pseudonimizado del alumno simulado (no corresponde a ninguna persona real).
- `modelo_personaje`: tramo de edad del TFM original (6-8 / 8-10 / 10-12), que fija la complejidad léxica y la longitud de guion esperada.
- `competencia_objetivo`: la competencia pragmática que se está entrenando en las sesiones de este perfil.
- `trayectoria_diseñada`: la etiqueta real (Progreso / Estancamiento / Regresión) y la sesión a partir de la cual se manifiesta.
- `rango_metricas`: cómo se mueven las cinco métricas a lo largo de la trayectoria (valores orientativos, se ajustan al generar el corpus).
- `nota_clinica_referencia`: justificación pedagógica del patrón, para que el perfil no sea arbitrario.

---

## Perfil 1 — Alumno simulado A (progreso estable)

| Campo | Valor |
|---|---|
| `student_id` | `sim-A01` |
| Edad / modelo de personaje | 7 años (tramo 6-8) |
| Competencia objetivo | Metáfora |
| Trayectoria diseñada | **Progreso** sostenido desde la sesión 1 |
| Sesiones simuladas | 15 |

**Evolución de métricas:**

| Métrica | Sesión 1-3 | Sesión 4-8 | Sesión 9-15 |
|---|---|---|---|
| aMLU | 2.5–3.0 | 3.2–3.8 | 4.0–4.6 |
| Latencia pragmática (LPP, ms) | 4500–5500 | 3500–4200 | 2500–3200 |
| IRC % | 15–25% | 30–40% | 45–55% |
| PEPE | 0.3–0.5 | 0.7–1.0 | 1.2–1.5 |
| %DET | 20–30% | 40–55% | 65–80% |

**Nota clínica de referencia:** perfil de progreso "de manual", coherente con un alumno sin comorbilidad añadida, con buena respuesta al entorno de baja ansiedad del chatbot (personajes estables, sin juicio, tal y como recoge el marco teórico sobre el valor del chatbot como espacio seguro). Sirve como caso de contraste frente a los perfiles 2 y 3.

---

## Perfil 2 — Alumno simulado B (estancamiento)

| Campo | Valor |
|---|---|
| `student_id` | `sim-B02` |
| Edad / modelo de personaje | 9 años (tramo 8-10) |
| Competencia objetivo | Sarcasmo |
| Trayectoria diseñada | Progreso hasta la sesión 7, **Estancamiento** desde la sesión 8 |
| Sesiones simuladas | 16 |

**Evolución de métricas:**

| Métrica | Sesión 1-7 | Sesión 8-16 |
|---|---|---|
| aMLU | 2.8 → 3.6 (progreso) | 3.5–3.7 (meseta, sin mejora neta) |
| Latencia pragmática (LPP, ms) | 5000 → 3800 (progreso) | 3700–3900 (estable, sin bajar) |
| IRC % | 20% → 38% (progreso) | 36–40% (meseta) |
| PEPE | 0.4 → 0.9 (progreso) | 0.85–0.95 (meseta) |
| %DET | 25% → 50% (progreso) | 48–52% (meseta) |

**Nota clínica de referencia:** el sarcasmo es, dentro de las cuatro competencias, la que exige mayor comprensión del contexto y del estado mental del interlocutor (Teoría de la Mente / atribución de estados mentales, línea de trabajo de Baron-Cohen sobre creencias de primer y segundo orden) — es razonable que sea la competencia con más riesgo real de estancamiento, y por eso se elige para este perfil. El propio corpus de referencias justifica por qué entrenar la ToM importa más allá de esta competencia concreta: "el déficit de ToM... sugiere que los problemas en comunicación, socialización e imaginación provienen de su incapacidad para representar y atribuir estados mentales... [y] puede conllevar la aparición de comorbilidades como depresión, trastornos de conducta, ansiedad" — lo que refuerza que una meseta sostenida en esta competencia concreta es clínicamente relevante y no solo un artefacto estadístico. La meseta no es un fallo del sistema, es el fenómeno que el clasificador debe aprender a detectar.

---

## Perfil 3 — Alumno simulado C (regresión)

| Campo | Valor |
|---|---|
| `student_id` | `sim-C03` |
| Edad / modelo de personaje | 11 años (tramo 10-12) |
| Competencia objetivo | Preguntas recíprocas |
| Trayectoria diseñada | Progreso hasta la sesión 9, **Regresión** desde la sesión 10 |
| Sesiones simuladas | 14 |

**Evolución de métricas:**

| Métrica | Sesión 1-9 | Sesión 10-14 |
|---|---|---|
| aMLU | 3.0 → 4.2 (progreso) | 3.9 → 3.3 (retroceso) |
| Latencia pragmática (LPP, ms) | 4800 → 3000 (progreso) | 3400 → 4300 (retroceso) |
| IRC % | 22% → 48% (progreso) | 44% → 28% (retroceso) |
| PEPE | 0.4 → 1.3 (progreso) | 1.1 → 0.6 (retroceso) |
| %DET | 22% → 70% (progreso) | 62% → 35% (retroceso) |

**Nota clínica de referencia:** la regresión simula un factor externo no observado por el sistema (p. ej. un cambio de rutina, un episodio de mayor ansiedad, o un factor de comorbilidad). El corpus de referencias documenta precisamente esta vía: el déficit de Teoría de la Mente "tiene un gran impacto en todas las áreas de desarrollo y puede conllevar la aparición de comorbilidades como depresión, trastornos de conducta, ansiedad", con "aumento de la ansiedad, aislamiento o conflictividad al encontrarse en un mundo social que no llegan a comprender del todo" — es decir, un empeoramiento pragmático no tiene por qué originarse en el propio entrenamiento, sino en factores externos de ansiedad/comorbilidad que el sistema no observa directamente. Es el caso más importante para la alerta temprana del terapeuta: un patrón de progreso sostenido que se invierte debe generar una señal clara, no diluirse en el ruido de la variabilidad normal.

---

## Perfil 4 — Alumno simulado D (progreso irregular / alta variabilidad)

| Campo | Valor |
|---|---|
| `student_id` | `sim-D04` |
| Edad / modelo de personaje | 8 años (tramo 6-8) |
| Competencia objetivo | Deixis |
| Trayectoria diseñada | **Progreso** con alta variabilidad sesión a sesión (sin meseta ni retroceso, pero con "dientes de sierra") |
| Sesiones simuladas | 15 |

**Evolución de métricas:**

| Métrica | Patrón |
|---|---|
| aMLU | Tendencia ascendente de 2.6 a 3.9, con oscilaciones de ±0.4 sesión a sesión |
| Latencia pragmática (LPP, ms) | Tendencia descendente de 5200 a 3400, con picos puntuales de hasta +800ms (sesiones "malas") |
| IRC % | Tendencia ascendente de 18% a 42%, con caídas puntuales de hasta -10 puntos |
| PEPE | Tendencia ascendente de 0.3 a 1.1, con varianza notable sesión a sesión |
| %DET | Tendencia ascendente de 20% a 60%, con caídas puntuales |

**Nota clínica de referencia:** este perfil es el más importante para **poner a prueba la robustez del clasificador**: una tendencia de progreso real pero con ruido alto no debería confundirse con estancamiento o regresión. Sirve también como aproximación al comportamiento esperado del grupo de control neurotípico (baseline de comparación en el dashboard). La elección de Deixis para este perfil está bien fundamentada: el uso desviado de pronombres personales, adverbios de lugar (aquí/allí) y de tiempo (ahora/después) es un rasgo pragmático específico y bien documentado del SA —"inversión pronominal" y "usa mal los pronombres personales (dice tú en vez de yo)" en checklists clínicos (Attwood)—, y al tratarse de elementos que en el desarrollo típico ya están consolidados a los 6-8 años, cualquier ruido en su dominio es informativo y no solo variabilidad de fondo. Ver Guion 4 en `Guiones_Dialogo.md`.

---

## Próximo paso

Con estos 4 perfiles (uno por cada combinación relevante: progreso limpio, estancamiento, regresión y progreso ruidoso) el generador de datos sintéticos de Marcos ya tiene una especificación completa para producir el corpus de sesiones. Quedaría pendiente, si el calendario lo permite, añadir un quinto perfil de "regresión leve reversible" (el alumno se recupera tras la alerta) para probar el caso de uso completo del dashboard, pero no es imprescindible para el mínimo de NF2.

Las cuatro competencias (Metáfora, Sarcasmo, Deixis, Preguntas recíprocas) tienen ya guion completo en `Guiones_Dialogo.md` (Guiones 1-4), con los tres tramos de edad cubiertos por tres personajes (Mona 6-8, Nico 8-10, Teo 10-12).

---

## Fuentes citadas (corpus de referencias unificado)

- Bartolucci, Pierce & Streiner (1980), citado en Martos & Ayuda (2002) — perfil lingüístico-pragmático del SA.
- Attwood, T. — *The Complete Guide to Asperger's Syndrome* — checklist de inversión pronominal.
- Corpus de referencias unificado — pasaje sobre el impacto del déficit de Teoría de la Mente en comorbilidades (depresión, ansiedad, trastornos de conducta).
