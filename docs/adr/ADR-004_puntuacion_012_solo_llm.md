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
| 3 | 104 (26 por tipo) | `gpt-oss:20b` | examen del LLM (12/10/2026); después se usó para afinar el modo simulado | sí: Marcos, con ayuda de Claude, 27/10/2026 (15 cambiadas; `docs/revision-bateria-3.md`) |
| 4 | 104 (26 por tipo) | Claude Sonnet 5.5 | examen a ciegas del modo simulado (25/10/2026), medida una vez | sí: Marcos, con ayuda de Claude, 27/10/2026 (1 cambiada; `docs/revision-bateria-4.md`) |

**Resultados medidos** (cifras copiadas de `docs/informe-validacion-metricas-reales.md` §10.6 y `docs/modo-simulado.md`):

| Evaluador | Batería | Buenas con 2 | Falsos 2 | Fecha / condiciones |
|---|---|---|---|---|
| LLM `qwen3:14b` + guarda (p3) | 3 (examen) | 69/78 (88,5 %) | 1/156 (0,6 %) | 12/10/2026, 3 repeticiones, GPU de Álvaro |
| LLM `qwen3:14b` + guarda (p3) | 2 | 88,9 % | 1,4 % | ídem |
| LLM `qwen3:14b` + guarda (p3) | 1 | 39/39 | 3/225 (1,3 %) | ídem |
| LLM `qwen3:14b` + guarda (p3) | 3 (examen) | 69/78 (88,5 %) | 0/156 con historial; 3/156 (1,9 %) sin él | 25/10/2026, 3 repeticiones, GPU de Álvaro, Ollama 0.40.11, código de las seis PR integradas |
| LLM `qwen3:14b` + guarda (p3) | 4 (a ciegas del simulado) | 78/78 (100 %) | 6/156 (3,8 %) con historial; 8/156 (5,1 %) sin él | ídem; primera medida con el LLM real |
| LLM `qwen3:14b` + guarda (p3) | 3 (examen, **etiquetas revisadas**) | 63/69 (91,3 %) en las dos condiciones | 0/159 (0 %) en las dos condiciones | 27/10/2026, 3 repeticiones, GPU de Álvaro (RTX 5060 Ti, 16 GB), Ollama 0.40.11, `main` en `cb12423`; sobre 1: 2/159 con historial y 3/159 sin él; fronterizas aceptables 83/84 con historial y 84/84 sin él |
| LLM `qwen3:14b` + guarda (p3) | 4 (a ciegas del simulado, **etiquetas revisadas**) | 78/78 (100 %) en las dos condiciones | 5/156 (3,2 %) con historial; 6/156 (3,8 %) sin él | ídem; sobre 1: 0/156 con historial y 1/156 sin él; fronterizas aceptables 71/78 (91,0 %) con historial y 69/78 (88,5 %) sin él |
| LLM `Qwen3-Coder-30B-A3B` (EXL3 3,34 bpw) + guarda (p3), `openai` por TabbyAPI | 3 (examen) | 75/78 (96,2 %) con historial; 73/78 (93,6 %) sin él | 19/156 (12,2 %) con historial; 16/156 (10,3 %) sin él | 26/10/2026, 3 repeticiones, GPU de Álvaro, código de las seis PR integradas; no cumple los umbrales del script |
| LLM `Qwen3-Coder-30B-A3B` (EXL3 3,34 bpw) + guarda (p3), `openai` por TabbyAPI | 4 (a ciegas del simulado) | 78/78 (100 %) en las dos condiciones | 8/156 (5,1 %) con historial; 13/156 (8,3 %) sin él | ídem; no cumple los umbrales sin historial |
| LLM falso (simulado) | 4 (a ciegas) | 21/26 (80,8 %) | 1/52 (1,9 %) | 25/10/2026, una pasada determinista |
| LLM falso (simulado) | 3 (ya afinada) | 24/26 | 5/52 | desarrollo, no cuenta como examen |

**Etiquetas revisadas el 27/10/2026 y nueva medida.** Las filas de la batería 3 anteriores a las dos últimas de `qwen3:14b` (LLM real el 12, 25 y 26/10 y modo simulado «ya afinada») se midieron con las etiquetas anteriores a la revisión (26 buenas y 52 malas) y no son comparables con la batería 3 revisada (23 buenas y 53 malas). Por eso se volvió a medir el 27/10/2026 con `qwen3:14b` sobre `main` en `cb12423` (las dos filas «etiquetas revisadas»; el evaluador es el mismo que el del 25/10, porque desde entonces solo cambió el límite de sesiones por semana). Resultado: la batería 3 sigue cumpliendo los dos objetivos (91,3 % de buenas con 2, por encima del 82 %, y 0 falsos 2 de 159, por debajo del 5 %), y la 4 da 78/78 y 3,2 % o 3,8 % de falsos 2. En la 4 la diferencia con el 25/10 (6/156 y 8/156) es de uno o dos casos con el mismo prompt, es decir, ruido del modelo y no una mejora; los falsos 2 son siempre los mismos dos casos («Que se le puso la sangre como el hielo en el cuerpo», de metáfora, y «A mi casa», de deixis). Las medianas de tiempo de la condición sin historial de esa jornada (2,07 s y 1,48 s, con p90 de 10 a 12 s) están infladas por otra tarea periódica del PC de Álvaro que también usa Ollama; no se citan como rendimiento. Con las etiquetas revisadas, el modo simulado da (27/10/2026, sin historial, una pasada): batería 3, 22/23 buenas y 3/53 falsos 2; batería 4, 21/26 y 1/52, igual que antes.

**Lo que NO está comprobado** (se declara en la memoria):
- Las baterías 3 y 4 se midieron con el LLM real el 25 y el 27/10/2026 (filas de arriba). Las repeticiones casi no aportan información: fallan los mismos casos las tres veces, así que la muestra efectiva es de 23 buenas y 53 malas en la batería 3 y de 26 y 52 en la 4. `LLM_PROVIDER=openai` se midió con las baterías 3 y 4 solo con TabbyAPI y otro modelo (`Qwen3-Coder-30B-A3B`, filas de arriba, 26/10/2026): da más falsos 2 que `qwen3:14b` y la batería 3 no cumple los umbrales, así que el evaluador **solo está validado con `qwen3:14b`**. No se midió el mismo modelo por los dos servidores, ni con vLLM ni con LM Studio.
- Las etiquetas de las baterías 3 y 4 las propuso una IA y las revisó una persona, Marcos, el 27/10/2026, con ayuda de otra IA (Claude), que propuso los cambios (16 etiquetas cambiadas; según él, la decisión en cada caso fue suya y no escribió las reglas ni el prompt). No es la anotación de un terapeuta, y la ayuda de la IA le resta independencia: los resultados siguen siendo provisionales (hojas en `docs/`). Las cifras del LLM real del 27/10/2026 ya usan las etiquetas nuevas.
- **No hay conversaciones reales anotadas** ni se ha medido el acuerdo con el terapeuta; las baterías son respuestas escritas, no habla de menores.
- El sesgo conocido del LLM es hacia **infravalorar** (ante la duda, 0): baja PEPE y %DET de alumnos que sí aciertan.

## Consecuencias
- La memoria cita las cifras del LLM real; las del modo simulado se citan siempre como «LLM falso, no el evaluador».
- Cambiar el prompt o el criterio cambia `evaluador_version` y obliga a repetir las baterías 2, 3 y 4.
- Para medir de nuevo el modo simulado hay que escribir una batería nueva (la 5) sin mirar sus reglas; no se afina con la 4.
- Si la revisión humana cambia etiquetas, se anotan las cifras antes y después; no se tocan las reglas para que suban.
