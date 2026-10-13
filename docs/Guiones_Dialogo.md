# Guiones de diálogo y personajes — SOCIAL-SIM Chat

**Tarea de reparto:** Álvaro García Puche — "Guiones de diálogo y personajes para cada competencia pragmática"
**Base teórica:** TFM 2020 (García Puche) — el chatbot funciona como espacio de práctica de bajo riesgo ("sin expectativas ni juicios", Wegerif, 2004), con personajes estables y predecibles que reducen la ansiedad, y una estructura de turno con códigos de comunicación claros: apertura, conversación, escucha, cierre y despedida.

**Actualización (revisión con corpus de referencias unificado):** el perfil pragmático del SA en la literatura clínica confirma exactamente las cuatro dificultades que este documento entrena — comprensión de actos de habla indirectos (metáforas, bromas, sarcasmo), uso de la deixis, y escaso/inadecuado uso de las preguntas recíprocas — con lenguaje retórico poco ajustado al interlocutor y ausencia de verbos mentalistas (Bartolucci, Pierce & Streiner, 1980; citado en Martos & Ayuda, 2002). Esta revisión también detectó y corrige una inconsistencia entre este documento y `Perfiles_Alumno_Simulado.md`: el Perfil B (sim-B02, Sarcasmo) tiene 9 años (tramo 8-10), pero el Guion 2 estaba escrito para "Teo" (tramo 10-12) — se resuelve incorporando el personaje pendiente para el tramo 8-10 (ver más abajo) en vez de dejarlo para Deixis, competencia que en realidad corresponde al Perfil D (6-8 años, ya cubierto por Mona).

Cada turno del guion tiene una figura pragmática **conocida por diseño** (el LLM local solo varía la forma de la frase, no introduce la figura); el sistema registra el tipo de respuesta del menor como: **0 = literal, 1 = asistida (con ayuda), 2 = correcta**.

---

## Personajes

### Personaje 1 — "Mona" (tramo 6-8 años)

- Vocabulario simple, frases cortas, tono cálido y paciente.
- Usada en el guion de **Metáfora** (perfil de alumno simulado A) y **Deixis** (perfil D).

### Personaje 2 — "Nico" (tramo 8-10 años)

- Vocabulario intermedio entre Mona y Teo; empieza a usar tono/contexto de forma más deliberada (necesario para que la figura del sarcasmo tenga sentido), pero manteniendo frases cortas y situaciones muy concretas y visuales.
- Usado en el guion de **Sarcasmo** (perfil de alumno simulado B, 9 años).
- **Nota de reparación:** este personaje resuelve el hueco que existía en la versión anterior de este documento (el Guion 2 usaba a "Teo", pensado para 10-12 años, para un perfil simulado de 9 años). Se recupera así la idea original de un personaje para el tramo 8-10, pero asignado a la competencia que realmente lo necesitaba (Sarcasmo, no Deixis).

### Personaje 3 — "Teo" (tramo 10-12 años)

- Vocabulario algo más elaborado, tono cercano de "amigo mayor", más directo.
- Usado en el guion de **Preguntas recíprocas** (perfil de alumno simulado C, 11 años).

---

## Estructura de un turno (aplica a todos los guiones)

1. **Apertura** — Mona/Teo saluda y sitúa el contexto de la actividad.
2. **Presentación de la figura** — se introduce la frase con metáfora/sarcasmo/etc.
3. **Pregunta al menor** — "¿qué crees que quiere decir...?" / "¿qué está pasando aquí?"
4. **Evaluación de la respuesta:**
   - **Correcta (2):** el chatbot valida y refuerza positivamente.
   - **Asistida (1):** si la respuesta es parcial o dudosa, el chatbot da una ayuda concreta (reformula, da una pista) y vuelve a preguntar.
   - **Literal (0):** si la respuesta es una interpretación literal de la figura, el chatbot no corrige de forma frontal — explica con calma el sentido no literal y ofrece un ejemplo.
5. **Cierre del turno** — se registra el evento (latencia, tipo de figura, resultado, ayudas pedidas) y se pasa al siguiente turno o se despide.

---

## Guion 0 — Apertura / toma de contacto (previo a cualquier competencia)

**Origen:** adaptado del Anexo A del TFM 2020 ("Cuestionario Fase 1 SA-chatbot"), que ya proponía una estructura de ramas condicionales según la respuesta del menor. Aquí se traduce esa misma lógica a variables y ramas explícitas, pensadas para poder cargarse directamente como un árbol de estados en el backend (encaja con el esquema de `session_data`: cada nodo es un turno con `figura=ninguna` — no hay competencia pragmática que evaluar, es solo apertura de sesión).

**Objetivo pedagógico:** iniciar la sesión con un intercambio predecible y de bajo riesgo antes de entrar en la práctica de una competencia concreta, reforzando el vínculo con el personaje estable (Mona o Teo, según el tramo de edad del alumno).

**Variables:** `{nombre_usuario}` se sustituye por el nombre (o alias pseudonimizado) del alumno al iniciar la sesión.

```
Turno 1 (Mona/Teo): "¡Hola {nombre_usuario}! Qué bien verte por aquí otra vez. ¿Cómo estás hoy?"
  → el menor responde (sin evaluación de figura, solo se registra si hay respuesta)

Turno 2 (Mona/Teo): "¿Te apetece que juguemos un poco antes de empezar?"
  Rama 2.A (respuesta negativa / "no puedo" / "no quiero"):
    → "Vale, no pasa nada. ¿Prefieres que hablemos de otra cosa, o pasamos ya a nuestro juego de palabras?"
  Rama 2.B (respuesta afirmativa):
    → "¡Genial! Vamos entonces con nuestro juego de palabras de siempre."
    (aquí se encadena con el Guion 1/2/3 de la competencia que toque esa sesión)

Turno 3 (Mona/Teo, solo si Rama 2.A): "¿Ha pasado algo hoy que te gustaría contarme?"
  Rama 3.A (el menor comparte algo):
    → Mona/Teo valida brevemente ("Qué interesante, gracias por contármelo") y pasa a la competencia
  Rama 3.B (no hay respuesta o respuesta muy breve):
    → "Vale, pues cuando quieras me lo cuentas. Ahora vamos con nuestro juego."

Cierre de apertura: "Venga, ¡vamos a practicar un poco juntos!" → transición al guion de competencia de la sesión.
```

**Nota de diseño:** a diferencia de los guiones 1-3 (que sí evalúan una figura pragmática concreta), este guion 0 no genera una etiqueta de acierto/error — solo registra si hubo respuesta y en qué rama avanzó la conversación. Sirve como "calentamiento" y como señal adicional de estado de ánimo/disposición del alumno esa sesión, útil como contexto para el terapeuta aunque no entre directamente en las 5 métricas del clasificador.

---

## Guion 1 — Metáfora (Mona, tramo 6-8 años)

**Objetivo pedagógico:** reconocer que una expresión no se refiere a su significado literal, en línea con la dificultad TEA/SA de comprensión de actos de habla indirectos —metáforas incluidas— documentada en la literatura clínica (Bartolucci, Pierce & Streiner, 1980; Martos & Ayuda, 2002).

| Turno | Figura | Frase de Mona | Ayuda si respuesta literal (0) | Ejemplo de respuesta correcta (2) |
|---|---|---|---|---|
| 1 | Metáfora | "¡Estoy que exploto de contenta hoy!" | "Mona no va a explotar de verdad — quiere decir que está MUY, muy contenta. ¿Se te ocurre otra forma de decir que alguien está muy feliz?" | "Que está muy contenta / muy feliz" |
| 2 | Metáfora | "Hoy tengo mariposas en el estómago." | "Mona no tiene mariposas de verdad dentro. Quiere decir que está un poco nerviosa. ¿Tú alguna vez has sentido eso antes de algo importante?" | "Que está nerviosa" |
| 3 | Metáfora | "Este ejercicio es pan comido." | "No hay pan de verdad — Mona quiere decir que el ejercicio es muy fácil para ella. ¿Qué palabra usarías tú para decir que algo es fácil?" | "Que es muy fácil" |
| 4 | Metáfora | "Se me heló la sangre cuando vi la sorpresa." | "La sangre de Mona sigue calentita — quiere decir que se asustó mucho de repente. ¿Qué otra palabra usarías para decir que alguien se asustó mucho?" | "Que se asustó / se sorprendió mucho" |

**Cierre del guion:** "Hoy hemos hablado de frases que no quieren decir exactamente lo que parece. ¡Lo has hecho genial, nos vemos la próxima vez!"

---

## Guion 2 — Sarcasmo (Nico, tramo 8-10 años)

**Objetivo pedagógico:** identificar cuándo el tono/contexto invierte el significado literal de una frase — la competencia con mayor exigencia de Teoría de la Mente entre las cuatro (atribución de estados mentales para reconocer una intención distinta de lo dicho literalmente), y por eso la de mayor riesgo de estancamiento (perfil de alumno simulado B, sim-B02). El perfil lingüístico del SA se caracteriza precisamente por "dificultades en la comprensión de actos de habla indirectos, tales como las metáforas, las bromas y el sarcasmo" (Bartolucci, Pierce & Streiner, 1980).

| Turno | Figura | Frase de Nico (con contexto) | Ayuda si respuesta literal (0) | Ejemplo de respuesta correcta (2) |
|---|---|---|---|---|
| 1 | Sarcasmo | *(Nico deja caer su bocadillo al suelo)* "¡Genial, justo lo que necesitaba hoy!" | "Piensa: ¿a Nico le gusta que se le caiga la comida? Cuando decimos lo contrario de lo que sentimos, a veces es sarcasmo. ¿Cómo crees que se siente Nico en realidad?" | "Que está molesto / fastidiado, no contento" |
| 2 | Sarcasmo | *(Después de perder un juego)* "Sí, se me da fenomenal esto." | "¿Nico ha ganado el juego? Cuando alguien pierde y dice que 'se le da fenomenal', normalmente está siendo irónico. ¿Qué crees que siente de verdad?" | "Que está frustrado, no que se le dé bien" |
| 3 | Sarcasmo | *(Lloviendo el día de la excursión)* "Qué suerte la nuestra, ¿eh?" | "¿Es buena suerte que llueva el día de la excursión? Nico lo dice al revés porque está un poco decepcionado. ¿Cómo dirías tú lo que siente?" | "Que tiene mala suerte / está decepcionado" |

**Cierre del guion:** "El sarcasmo es de las cosas más difíciles de pillar, ¡y hoy has estado muy atento! Seguimos la próxima sesión."

---

## Guion 3 — Preguntas recíprocas (Teo, tramo 10-12 años)

**Objetivo pedagógico:** iniciar y sostener el turno conversacional devolviendo una pregunta al interlocutor (IRC — Índice de Reciprocidad Conversacional), abordando la dificultad de "iniciativa para comenzar" relaciones/conversaciones señalada en el marco teórico (Wing, 1981).

| Turno | Figura | Frase de Teo | Ayuda si no hay reciprocidad (0) | Ejemplo de respuesta correcta (2) |
|---|---|---|---|---|
| 1 | Pregunta recíproca | "Hoy he jugado al fútbol en el recreo, ¡me ha encantado! ¿Y tú, qué has hecho?" | "Te he contado algo mío — ahora te toca a ti contarme algo, o preguntarme algo de vuelta. ¿Qué has hecho tú hoy?" | El menor comparte algo propio o pregunta a Teo de vuelta |
| 2 | Pregunta recíproca | "Mi color favorito es el azul. ¿Cuál es el tuyo?" | "Te he preguntado por tu color favorito — ¿me lo dices?" | El menor responde con su color y, idealmente, pregunta algo a Teo |
| 3 | Pregunta recíproca | "Estoy un poco cansado hoy. ¿Tú cómo estás?" | "Te he dicho cómo me siento yo. ¿Y tú, cómo te sientes hoy?" | El menor responde sobre su propio estado |

**Cierre del guion:** "Me ha gustado mucho hablar contigo hoy y saber cosas de ti. ¡Hasta la próxima!"

---

## Guion 4 — Deixis (Mona, tramo 6-8 años)

**Objetivo pedagógico:** identificar y usar correctamente los elementos deícticos (pronombres personales, adverbios de lugar y de tiempo) cuyo significado depende de quién habla, cuándo y desde dónde. Corresponde al perfil de alumno simulado D (sim-D04, 8 años).

**Base clínica (corpus de referencias):** el uso desviado de la deixis está documentado como rasgo específico del perfil lingüístico del SA — "dificultades en el uso de la deixis y de vocabulario abstracto" junto con las dificultades de actos de habla indirectos (Bartolucci, Pierce & Streiner, 1980; Martos & Ayuda, 2002) — y se manifiesta clínicamente como **inversión pronominal** (p. ej. "ecolalia, perseveración, inversión pronominal y entonación anormal" como rasgo del habla en TEA) y en checklists diagnósticos como el ítem "usa mal los pronombres personales (dice tú en vez de yo, quieres en vez de quiero)" (Attwood). El objetivo de adquisición de pronombres YO/TÚ, posesivos MÍO/TUYO y adverbios de lugar AQUÍ/ALLÍ aparece también como hito de intervención temprana en el lenguaje (tablas de niveles de desarrollo del lenguaje, corpus de referencias), lo que confirma que son elementos que a esta edad ya deberían estar consolidados y por tanto son un buen indicador de dificultad pragmática específica cuando no lo están.

| Turno | Figura | Frase/situación de Mona | Ayuda si hay error deíctico (0) | Ejemplo de respuesta correcta (2) |
|---|---|---|---|---|
| 1 | Deixis personal (pronombres) | "Cuéntame algo que hayas hecho hoy. Recuerda: cuando hablas de ti mismo, dices 'yo'." | *(si el menor invierte el pronombre, p. ej. "tú fuiste al parque" queriendo decir que fue él)* "Cuando hablas de ti, se dice 'yo fui', no 'tú fuiste'. ¿Puedes contármelo otra vez empezando por 'Yo...'?" | El menor relata el evento usando correctamente "yo" para referirse a sí mismo |
| 2 | Deixis temporal | "Ahora vamos a jugar a algo. Cuando yo diga 'ya está', paramos. ¿Qué crees que significa 'ahora' en lo que te acabo de decir?" | "'Ahora' quiere decir 'en este mismo momento en que hablamos', no mañana ni ayer — es una palabra que cambia según cuándo se dice." | "Que es en este momento / ya mismo" |
| 3 | Deixis espacial/discursiva | *(mini-relato)* "Había una vez un perrito que vivía en una casa. Un día dijo: 'mañana voy a venir aquí a jugar'. ¿A qué lugar se refiere 'aquí'?" | "'Aquí' señala el lugar donde está quien habla en ese momento — en el cuento, la casa del perrito. Si yo dijera 'aquí' ahora mismo, ¿a qué me estaría refiriendo?" | "A la casa del perrito / al sitio donde está él cuando lo dice" |

**Cierre del guion:** "Hoy hemos practicado unas palabras que cambian de significado según quién habla, cuándo y dónde. ¡Lo has hecho genial!"

**Nota de diseño:** a diferencia de los guiones 1-3, aquí la "figura" no es una expresión no literal sino una referencia cuyo significado depende del contexto de enunciación — el error característico no es la interpretación literal, sino resolver el deíctico con el referente equivocado o no resolverlo. Se mantiene la misma codificación 0/1/2 para no romper el esquema del clasificador.

---

## Pendiente

- Validar con Marcos el formato exacto en que estos guiones (incluido el Guion 0 de apertura) se cargarán en el sistema (JSON por turno/rama, tabla en base de datos, etc.) para que encajen con el esquema de `session_data`.
- Revisar si conviene adaptar también la Sesión 2 del Anexo A del TFM 2020 (más centrada en amistades/despedida) como un Guion 0-bis para sesiones posteriores a la primera.
- Ampliar el Guion 4 (Deixis) con más turnos si en la validación con Marcos se ve corto frente a los Guiones 1-3 (actualmente 3 turnos vs. 3-4 de los demás; es coherente pero podría beneficiarse de un turno adicional de deixis espacial en primera persona, p. ej. "yo estoy aquí" vs. "tú estás ahí", una vez decidido cómo representar la referencia espacial en un chat de texto sin cuerpo/posición física).

---

## Fuentes citadas (corpus de referencias unificado)

- Bartolucci, Pierce & Streiner (1980), citado en Martos & Ayuda (2002) — perfil lingüístico-pragmático del SA (actos de habla indirectos, deixis, preguntas repetitivas).
- Attwood, T. — *The Complete Guide to Asperger's Syndrome* — checklist de signos diagnósticos, ítem de inversión pronominal y técnica de "susurrar" para el andamiaje de preguntas recíprocas (base del mecanismo de ayuda del Guion 3).
- Lorna Wing (1981, y Burgoine & Wing 1983) — primera caracterización clínica del síndrome, base de la dificultad de iniciar/mantener conversación recíproca citada en el Guion 3.
