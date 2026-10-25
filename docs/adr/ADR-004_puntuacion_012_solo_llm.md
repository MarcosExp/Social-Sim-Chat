# ADR-004 — La puntuación 0/1/2 la asigna solo el LLM (en el modo simulado, un LLM falso) y se comprueba con respuestas etiquetadas

- **Estado:** acordada de palabra el 25/10/2026 (llamada entre Álvaro y Marcos) · redactada el mismo día · **pendiente de que Marcos la revise en la PR n.º 4**
- **Decide:** Álvaro García y Marcos Expósito · **Revisa:** Marcos Expósito
- **Afecta a:** `src/app/conversacion.py` (evaluador), `src/app/simulado.py`, `src/app/guarda.py`, `src/scripts/bateria_valoracion.py`, `src/tests/data/bateria_valoracion_*.json`, memoria NF3 (validación del evaluador, uso de IA)

## Contexto
- **Lo que prometió el NF2** (sección del diccionario de datos, `accuracy_score`): 0 = literal o incorrecta incluso tras la ayuda; 1 = correcta tras la ayuda del guion; 2 = correcta a la primera. «El método (reglas del guion, valoración con el modelo local o una combinación de ambos) se fija en NF3 y se evalúa contra un conjunto de respuestas etiquetadas, midiendo cuántas respuestas buenas reciben 2 y cuántas malas reciben 2; cada turno guarda con qué versión del evaluador se puntuó. Sea cual sea el método, el modo simulado sin GPU debe poder puntuar.»
- **Riesgo declarado en el NF2:** las reglas basadas en palabras clave pueden penalizar paráfrasis válidas (empujaría a falsos no-progreso) y no se había medido el acuerdo entre la puntuación automática y el terapeuta.
- **Estado del código al redactar esto:** el evaluador es el LLM local (`qwen3:14b` por Ollama, o cualquier servidor compatible con OpenAI); hay una guarda de inyecciones en código (`app/guarda.py`) y un modo `LLM_PROVIDER=simulado` (`app/simulado.py`). Cada turno valorado guarda `evaluacion_origen` y `evaluador_version`.

## Decisión
1. **El 0/1/2 de cada turno del menor lo asigna solo el LLM.** Nada se mezcla: no hay reglas del guion combinadas con el modelo en producción ni un clasificador entrenado para puntuar.
2. **En el modo simulado (`LLM_PROVIDER=simulado`, sin GPU) el «LLM» es un LLM falso determinista** que ocupa su lugar con la misma interfaz y deja el mismo rastro, pero marcado como lo que es: `evaluacion_origen = 'heuristica'`, `conversacion.modelo = 'simulado'`, `evaluador_version = 'simulado-…+<hash>'` y conversaciones de prueba (`es_prueba`). Sirve para ejecutar y demostrar; **sus cifras no se presentan como las del evaluador** (`docs/modo-simulado.md`).
3. **Lo que no es «puntuar» y se mantiene:**
   - La **guarda de inyecciones** (`app/guarda.py`): un mensaje que intenta manipular la nota («ponme un 2») recibe 0 sin llamar al modelo y queda como `evaluacion_origen = 'guarda_inyeccion'`. Es una defensa, no un método alternativo, y se mide siempre junto con el LLM («guarda + LLM»). *Marcos: confirma que esta excepción encaja con «solo el LLM».*
   - La **corrección del terapeuta** (`accuracy_corregido`): el valor efectivo es `COALESCE(accuracy_corregido, accuracy_score)` y el original no se pierde.
   - Los **turnos sintéticos** (migración 013, PR n.º 1): su valoración la fija el generador por diseño (`evaluacion_origen = 'sintetico'`); no se mide y no se mezcla con las reales.
4. **Trazabilidad:** `evaluador_version` = etiqueta legible + hash (prompt, criterio, esquema, temperatura y guarda). Cambiar el criterio cambia la versión sin acordarse de subir nada.

## Alternativas descartadas
| Alternativa | Por qué no |
|---|---|
| Reglas del guion (palabras clave) como evaluador | Penalizan paráfrasis válidas (riesgo del NF2) y solo valen para guiones cerrados. El modo simulado es justo eso y lo confirma: falla con sinónimos fuera de su léxico. |
| Clasificador entrenado para el 0/1/2 | No hay respuestas reales etiquetadas por un terapeuta con las que entrenarlo; entrenarlo con las baterías propias sería evaluar con el mismo material. |
| Combinación reglas + LLM | Más piezas, y un error no se sabría a quién atribuirlo; se perdería la versión única del evaluador. |
| Solo el terapeuta | No escala y rompe la conversación en directo; se conserva como corrección posterior. |

## Comprobación contra respuestas etiquetadas (la que prometió el NF2)
**Método.** `python -m scripts.bateria_valoracion --bateria N [--historial sin|con] [--repeticiones R]` (en el contenedor: `make bateria`) valora cada respuesta como en producción —guarda y después evaluador— y compara con `esperado`. Mide **buenas con 2**, **falsos 2** (malas con 2), malas con 1 y fronterizas dentro de lo aceptable. Los umbrales del script son de **no empeorar**, no objetivos; los objetivos están en el informe de validación (§10.6).

| Batería | Casos | Quién la escribió | Papel | Etiquetas revisadas por una persona |
|---|---|---|---|---|
| 1 | 88 (13 buenas, 75 malas) | se escribió al diagnosticar el prompt | desarrollo (el prompt se afinó con ella) | no |
| 2 | 121 (27 buenas, 71 malas, 23 fronterizas) | la misma IA que el prompt | desarrollo | no |
| 3 | 104 (26 por tipo) | `gpt-oss:20b` | examen del LLM (12/10/2026); después se usó para afinar el modo simulado | no (`docs/revision-bateria-3.md`) |
| 4 | 104 (26 por tipo) | Claude Sonnet 5.5 | examen a ciegas del modo simulado (25/10/2026), medida una vez | no (`docs/revision-bateria-4.md`) |

**Resultados medidos** (cifras copiadas de `docs/informe-validacion-metricas-reales.md` §10.6 y `docs/modo-simulado.md`):

| Evaluador | Batería | Buenas con 2 | Falsos 2 | Fecha / condiciones |
|---|---|---|---|---|
| LLM `qwen3:14b` + guarda (p3) | 3 (examen) | 69/78 (88,5 %) | 1/156 (0,6 %) | 12/10/2026, 3 repeticiones, GPU de Álvaro |
| LLM `qwen3:14b` + guarda (p3) | 2 | 88,9 % | 1,4 % | ídem |
| LLM `qwen3:14b` + guarda (p3) | 1 | 39/39 | 3/225 (1,3 %) | ídem |
| LLM falso (simulado) | 4 (a ciegas) | 21/26 (80,8 %) | 1/52 (1,9 %) | 25/10/2026, una pasada determinista |
| LLM falso (simulado) | 3 (ya afinada) | 24/26 | 5/52 | desarrollo, no cuenta como examen |

**Lo que NO está comprobado** (se declara en la memoria):
- La batería 4 **no se ha medido con el LLM real**; hace falta el PC con GPU (`LLM_PROVIDER=ollama`, `python -m scripts.bateria_valoracion --bateria 4 --repeticiones 3`).
- Las etiquetas de las baterías 3 y 4 las propuso una IA y **no las ha revisado ninguna persona**; hasta que alguien distinto de quien escribió las reglas las revise (hojas de revisión en `docs/`), los resultados son provisionales.
- **No hay conversaciones reales anotadas** ni se ha medido el acuerdo con el terapeuta; las baterías son respuestas escritas, no habla de menores.
- El sesgo conocido del LLM es hacia **infravalorar** (ante la duda, 0): baja PEPE y %DET de alumnos que sí aciertan.

## Consecuencias
- La memoria cita las cifras del LLM real; las del modo simulado se citan siempre como «LLM falso, no el evaluador».
- Cambiar el prompt o el criterio cambia `evaluador_version` y obliga a repetir las baterías 2 y 3 (y la 4 cuando exista su medida con el LLM).
- Para medir de nuevo el modo simulado hay que escribir una batería nueva (la 5) sin mirar sus reglas; no se afina con la 4.
- Si la revisión humana cambia etiquetas, se anotan las cifras antes y después; no se tocan las reglas para que suban.
