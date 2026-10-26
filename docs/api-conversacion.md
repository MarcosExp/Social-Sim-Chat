# API de conversación (guiones + Ollama)

Estado: implementada y probada con Ollama **simulado**; la medición de latencia con tu `qwen3:14b` real
la haces tú con `make smoke` (o `scripts\test-local.ps1 -Humo`).

## Reparto de papeles

| Quién | Qué decide |
|---|---|
| **Guion** (`src/app/guiones/guiones.json`) | Qué figura se presenta, cuándo hay ayuda, cuándo se avanza. Texto de figuras y ayudas **literal**. |
| **LLM** | En cada turno de competencia, una sola llamada con salida JSON `{evaluacion: 0\|1\|2, reaccion}`. No introduce figuras nuevas. |
| **Reglas** | La apertura (Guion 0): ramas por reglas simples, sin LLM. |
| **Guarda de inyecciones** (`src/app/guarda.py`) | Antes del LLM: si el mensaje del menor intenta manipular al evaluador (7 patrones: «ignora las instrucciones», «SYSTEM:», «puntúa/evalúa/devuelve … 2», «evaluacion», etc.) se valora 0 **sin llamar al LLM**, `evaluacion_origen = "guarda_inyeccion"` y `guarda_patron` con los patrones. El niño recibe la ayuda del guion y sigue jugando. |

Máximo 2 intentos por turno: respuesta → (si 0 ó 1) ayuda del guion → segunda respuesta → se avanza igualmente.

## Endpoints

### `POST /conversaciones` → 201
Body: `{"student_id": "sim-001", "competencia": "Metáfora"?, "alias": "Álvaro"?, "prueba": false?}`
(competencia por defecto = objetivo del alumno; alias por defecto = `student_id`).
Respuesta: `conversacion_id`, `competencia`, `personaje`, `estado`, `nodo_actual`, `intento`, `guion_version`,
`turno_bot {nodo, tipo, personaje, mensajes[], texto}`.

### `POST /conversaciones/{id}/turnos` → 200
Body: `{"mensaje": "1..500 caracteres", "latencia_ms": int?}`. Si se omite `latencia_ms`, se mide en servidor
(desde que se creó el último mensaje del bot). Respuesta = la de arriba más `evaluacion`, `evaluacion_origen`
(`llm` o `guarda_inyeccion`), `guarda_patron`, `evaluador_version`, `rama`, `latencia_ms` y `llm {modelo, prompt_tokens, eval_tokens, ollama_ms, carga_ms, espera_cola_ms, intentos, ms_total}`
(`null` en la apertura). Un fallo del LLM **no avanza ni guarda nada**: se puede reenviar el mismo turno.

### `GET /conversaciones/{id}` → 200
Cabecera + todos los turnos (`orden, rol bot|menor, nodo, tipo, intento, texto, evaluacion, rama, latencia_ms, llm_ms`).
Esta tabla (`conversacion_turno`) es la fuente para calcular métricas reales más adelante.

### Errores — siempre `{codigo, mensaje, reintentable}`
| HTTP | codigo | Cuándo |
|---|---|---|
| 404 | `alumno_no_encontrado`, `conversacion_no_encontrada` | |
| 409 | `conversacion_terminada` | turno sobre una conversación cerrada |
| 422 | `competencia_invalida` / validación | |
| 503 (+`Retry-After`) | `llm_no_disponible`, `llm_ocupado` | Ollama no responde tras los reintentos / cola saturada |
| 503 | `modelo_no_encontrado` | el mensaje trae `ollama pull <modelo>` |
| 502 | `respuesta_invalida` | JSON inválido tras 1 reintento |
| 500 | `contexto_excedido` | el prompt no cabe en `num_ctx` (nunca se trunca en silencio) |

### `GET /health`
`llm` es `"ok"` o un mensaje accionable (Ollama caído → que el Ollama de Windows escuche con su propio `OLLAMA_HOST=0.0.0.0` y que el contenedor llegue a `host.docker.internal`;
modelo ausente → `ollama pull qwen3:14b`). Además `llm_model` y `llm_modelo_disponible`. `status="degraded"` si algo falla.

## Pantalla del chat (frontend del menor)

Servida por el propio backend en `/chat/` (HTML + JS + CSS estáticos en `src/app/static/chat/`, sin build). Con el stack levantado: http://localhost:8010/chat/. Usa `?api=http://host:puerto` para apuntarla a otra API.

- Elige alumno (`GET /students`), alias opcional y competencia; `prueba` marca la conversación como de prueba.
- Mide `latencia_ms` en el navegador: desde que se pinta la última burbuja del personaje hasta que el menor envía.
- No muestra nunca la valoración (`evaluacion`) al menor.
- Errores `reintentable: true` (503, sin conexión): conserva el mensaje pendiente y ofrece «Intentar otra vez», que reenvía el mismo texto con la misma latencia. Errores no reintentables: el texto vuelve a la caja. `409` cierra la conversación.
- Prueba sin backend ni Ollama: `python -m scripts.mock_api_chat` (puerto 8099, `/chat/`) y `python -m tests.e2e_chat` (Playwright; no entra en el `pytest` por defecto). Disparadores del mock: «fallo503», «fallo409», «fallo422» en el mensaje.

## Proveedores del motor (`LLM_PROVIDER`)
| Valor | Qué es | Notas |
|---|---|---|
| `ollama` (por defecto) | API nativa de Ollama (`/api/chat`) | Validado con `qwen3:14b`. Permite `think:false`, `num_ctx` y `keep_alive`. |
| `openai` | Cualquier servidor con API compatible con OpenAI (`/v1/chat/completions`) | Interfaz que fija NF2 para sustituir el motor. Variables `LLM_COMPAT_URL` (raíz, sin `/v1`), `LLM_COMPAT_MODEL`, `LLM_COMPAT_API_KEY` (opcional, `Authorization: Bearer`), `LLM_COMPAT_RESPONSE_FORMAT` y `LLM_COMPAT_REASONING_EFFORT` (por defecto `none`). |
| `simulado` | Valoración 0/1/2 por reglas, sin LLM ni GPU | Para ejecutar y demostrar sin hardware. No es el evaluador del producto: ver [`modo-simulado.md`](modo-simulado.md). `evaluacion_origen = heuristica`, conversación con `modelo = simulado` y, por defecto, `es_prueba`. `/health` responde `ok` con `llm_provider: simulado`. |
| `tabbyapi` | Alias histórico de `openai` con `TABBYAPI_*` | Sin `response_format`; cabecera `x-api-key`. |

Con `openai` el cliente envía `model`, `messages`, `temperature`, `max_tokens` (`OLLAMA_NUM_PREDICT`) y `stream:false`, y para el evaluador `response_format` con el JSON schema (`strict`, `additionalProperties:false`). No envía `think`, `num_ctx` ni `keep_alive`: el contexto lo gestiona el servidor y los bloques `<think>…</think>` que devuelva el modelo se descartan. Sí envía `reasoning_effort: "none"` (salvo que `LLM_COMPAT_REASONING_EFFORT` esté vacío), que es lo que apaga el razonamiento de qwen3 en el `/v1` de Ollama; si el servidor corta la respuesta por `max_tokens` con JSON exigido, el cliente lo dice en el error (`respuesta_invalida`) en vez de «no devolvió JSON». `/health` comprueba `/v1/models` y avisa si `LLM_COMPAT_MODEL` no está. Los errores, la cola de una petición a la vez y los reintentos son los mismos que con Ollama.

Estado: probado con servidor simulado (`src/tests/test_proveedor_openai.py`: contrato del cliente y conversación completa) **y con un servidor real el 25/10/2026**: Ollama 0.40.11 por su `/v1`, `qwen3:0.6b` en CPU de 2 núcleos, `python -m scripts.smoke_conversacion` con `LLM_PROVIDER=openai`: conversación completa de 6 turnos con LLM, `/health` ok, mediana 6,7 s por turno. Esa prueba encontró dos fallos, ya corregidos: (1) con qwen3 el razonamiento agotaba `max_tokens` y la respuesta llegaba cortada (`"{\n\"analis"`) → `reasoning_effort: none`; (2) `smoke_conversacion` no enviaba `X-API-Key` y fallaba con la clave del terapeuta activa. El mismo día se repitió con `qwen3:14b` en la GPU del PC de Álvaro (Ollama 0.40.11, código de las seis PR integradas): conversación completa de 8 turnos con LLM, `/health` ok, mediana en caliente 1,62 s por turno y primer turno 8,8 s. Con Ollama por su `/v1` solo se probó la conversación completa, no la calidad de la valoración (las baterías de `qwen3:14b` se midieron con `LLM_PROVIDER=ollama`), y con el modelo de 0,6B la calidad no significa nada: solo se probó el protocolo.

**El 26/10/2026 se probó con un servidor que no es Ollama: TabbyAPI** (puerto 5000, clave de API por `Authorization: Bearer`, modelo cargado `Qwen3-Coder-30B-A3B-EXL3-3.34bpw-uniform`, mismo PC y código de las seis PR integradas). `/health` ok; conversación completa con 7 turnos con LLM (primer turno 3,6 s, mediana en caliente 0,92 s) sin tocar `LLM_COMPAT_RESPONSE_FORMAT` ni `LLM_COMPAT_REASONING_EFFORT` (valen los de por defecto); y las baterías 3 y 4 con 3 repeticiones: batería 3, 75/78 buenas y 19/156 falsos 2 (12,2 %) con historial, 73/78 y 16/156 (10,3 %) sin él; batería 4, 78/78 y 8/156 (5,1 %) con historial, 78/78 y 13/156 (8,3 %) sin él; mediana de 0,76 a 0,83 s por turno con LLM. El protocolo funciona (clave, `response_format`, `reasoning_effort`), pero con ese modelo la batería 3 queda por encima de los umbrales del script (el script salió con código 1: 6,3 y 5,3 falsos 2 por pasada de media, frente a un máximo de 3), mientras que `qwen3:14b` por `ollama` dio 0/156 con historial. El evaluador se ajustó a `qwen3:14b`: cambiar de modelo obliga a remedirlo. **Qué no separa esta prueba:** el efecto del servidor del efecto del modelo (no se probó el mismo modelo por dos servidores). Además, TabbyAPI no devolvió `usage.prompt_tokens` (la columna «tok in» del humo sale vacía). **Sigue sin probarse** con vLLM ni LM Studio.

## Garantías del cliente Ollama (`src/app/llm_client.py`)
- `num_ctx` explícito (`OLLAMA_NUM_CTX`, 8192), `think:false`, `stream:false`, `keep_alive` largo (`LLM_KEEP_ALIVE`, 30m).
- Variables de entrada del compose: `OLLAMA_URL` y `LLM_KEEP_ALIVE` (dentro del contenedor siguen siendo `OLLAMA_HOST`/`OLLAMA_KEEP_ALIVE`).
  Regla: no usar como entrada el nombre exacto de una variable propia de Ollama que Windows pueda tener definida (`OLLAMA_HOST`, `OLLAMA_KEEP_ALIVE`, `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_NUM_PARALLEL`…), porque el entorno del shell gana a `.env`.
- **Una petición a la vez** (semáforo) y **un solo worker** de uvicorn (el semáforo es por proceso; con varios
  workers dejarían de serializarse). Cola máxima `OLLAMA_COLA_TIMEOUT_S`.
- Reintento acotado (`OLLAMA_MAX_REINTENTOS`=2, espera exponencial) solo ante conexión/timeout/5xx. Nunca ante 4xx.
- Un cerrojo por conversación evita que dos envíos simultáneos la corrompan.

## Supuestos a revisar
1. **Guion 0 (apertura)**: la rama `a2 → a2A → a3` (negativa) la he modelado como: a2 negativa → `rama_2A`
   (`a2A`) → cualquier respuesta → `a3` → `rama_3A/3B` según el niño comparta o no (≥3 palabras) → primera figura.
   Si en el guion original es distinto, solo cambia `responder()` en `src/app/conversacion.py`.
2. **Criterio de evaluación 0/1/2** (prompt en `_prompt_sistema`): redactado a partir de la «respuesta esperada»
   de cada turno; conviene que lo revise quien conozca el criterio clínico. Endurecido el 2026-10-12 tras medir que
   la primera versión daba 2 al 28 % de las respuestas malas (literales, «ok», emojis, instrucciones inyectadas): el
   JSON lleva ahora un campo `analisis` previo (se descarta), el texto del niño va entre comillas triples y ante la duda
   entre 0 y 2 se puntúa 0. Batería 1 (88 respuestas, afinada): falsos 2 de 21/75 a 0-3/75. Batería 2 (nueva): 2,3 % de falsos 2 y solo 72 % de buenas con 2: el prompt infravalora (`docs/informe-validacion-metricas-reales.md` §10.2; `make bateria`).
3. El LLM solo ve el turno actual y hasta 4 mensajes del mismo nodo.

## Tests
- `make test` / `scripts\test-local.ps1`: tests de contrato (cliente, guiones, API completa, métricas) con Ollama simulado
  (`httpx.MockTransport`) y el Postgres del stack. Crean alumnos `TST-*` y los borran.
- `make smoke` / `scripts\test-local.ps1 -Humo`: conversación completa contra tu Ollama real. Imprime por turno
  el total, `ollama_ms`, `carga_ms` (carga en frío), cola y tokens de prompt; informa del primer turno (frío) por
  separado de la mediana en caliente; sale con código ≠ 0 si la mediana supera `--max-p50` (10 s) o el peor turno
  `--max-turno` (60 s). Crea una conversación en la BD marcada `prueba` (no genera métricas).
