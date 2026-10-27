# SOCIAL-SIM Chat — prototipo para la entrega NF3 (Grupo 12)

Entrenador conversacional y *learning analytics* para menores con TEA / síndrome de Asperger (6-12 años).
Módulo C088 · Curso de Especialización en IA y Big Data (iFP) · Grupo 12: Álvaro García Puche y Marcos Expósito Flox.

> **Prototipo académico, sin validez clínica.** Los datos del clasificador son sintéticos; las sesiones «reales» son
> conversaciones de prueba. Licencia: **PolyForm Noncommercial 1.0.0** (uso no comercial; ver [`LICENSE`](LICENSE)
> y [`AUTORIA.md`](AUTORIA.md)).

## Qué hay aquí (implementado y probado)

| Pieza | Dónde | Estado |
|---|---|---|
| Base de datos PostgreSQL 16, migraciones 001→013 | `data/init-db/` | Implementada. ER v2: una sola tabla `session_data` con `origen` (`sintetico`/`real`) |
| Backend FastAPI (alumnos, sesiones, conversación, correcciones, modelo, predicciones, resumen) | `src/app/` | Implementado. Contrato: [`docs/api-dashboard.md`](docs/api-dashboard.md), [`docs/api-conversacion.md`](docs/api-conversacion.md) |
| Chat del menor (HTML estático servido por el backend) | `src/app/static/chat/` → `http://localhost:8010/chat/` | Implementado; **necesita un LLM** (Ollama) para responder |
| Dashboard del terapeuta (Streamlit, solo habla con la API) | `src/dashboard/` → `http://localhost:8501` | Implementado |
| Generador de corpus sintético y evaluación antifuga | `src/generador/`, `src/ml/` | De Marcos; la única modificación en este repositorio es la columna `nivel_ruido` del generador (`src/generador/ORIGEN.md`) |
| Turnos sintéticos de cada sesión | `src/scripts/generar_turnos.py` (de Marcos), llamado al final de `seed_corpus.py` | Implementado; `--sin-turnos` los omite |
| Clasificador (RandomForest, CV por alumno, anti-fuga) | `src/scripts/train_classifier.py` | Implementado; entrena offline y escribe la predicción en `session_data` |
| Vista `turn_data` (una fila por figura, regla 2/1/0) | migración 009 | Implementada (conversaciones reales y turnos sintéticos) |
| Tests | `src/tests/` | Pasan (`make test`; el recuento lo da pytest y no se copia aquí para que no quede desactualizado); usan un Ollama simulado (`tests/fake_ollama.py`) |

## Diseñado pero NO implementado (límites conocidos)

- **Turnos sintéticos:** `generar_turnos.py` los deriva de las métricas de cada sesión (texto de relleno; conversaciones `origen='sintetico'` y `es_prueba`, que no entran en las métricas reales ni en el entrenamiento). Al recalcular las métricas desde los turnos, la diferencia con las de la sesión es de mediana 0,08 en PEPE, 0,06 en aMLU y 3,0 puntos en IRC (máximo 10,1), y el %DET del diseño no se reproduce: el propio script lo declara. El dashboard no muestra estos turnos.
- **Predicción sobre sesiones reales:** no se hace. `GET /students/{id}/prediccion` devuelve `disponible:false` con los motivos (hacen falta 4 sesiones reales, `pct_DET` es provisional, el evaluador del 0/1/2 no está validado).
- **Autenticación:** una clave compartida (`X-API-Key`) y un nombre de autor (`X-Terapeuta`) sin verificar. No hay usuarios ni roles.
- **Silencios** del menor no se registran; la **nota clínica no está cifrada**; no hay predicción en línea.
- **Del diseño del NF2 sin hacer:** el baseline neurotípico simulado del dashboard (historia 8, que el plan del NF2 situaba después del NF3), la recomendación adaptativa para la siguiente sesión y el límite de duración de cada sesión. El límite de sesiones por semana sí existe, pero apagado por defecto (`MAX_SESIONES_SEMANA`, ver arriba).
- **Margen estrecho del clasificador:** cumple los umbrales (F1-macro ≥ 0,75, recall y precisión de estancamiento ≥ 0,65) con la semilla por defecto, pero el recall de estancamiento queda cerca del límite y varía con la semilla (réplica de 10 semillas en `docs/validacion/`).
- El evaluador 0/1/2 (LLM) se validó con baterías propias, no con conversaciones reales anotadas: [`docs/informe-validacion-metricas-reales.md`](docs/informe-validacion-metricas-reales.md).
- Las fórmulas de las métricas reales son una propuesta explícita y revisable: [`docs/metricas-reales.md`](docs/metricas-reales.md).

## Arrancarlo sin GPU (solo con este README)

Requisitos: Docker (con Compose v2). Linux/macOS/WSL: `make`. Windows sin make: ver más abajo.

```bash
git clone https://github.com/cCoolBoox/social-sim-chat-nf3 && cd social-sim-chat-nf3
make up       # crea environment/.env si falta, construye y levanta Postgres + backend + dashboard
make seed     # genera el corpus sintético (100 alumnos, 1500 sesiones) y lo carga en Postgres
make train    # entrena el clasificador y escribe las predicciones (~30 s)
make verify   # conteos en BD (100 / 1500 / 1200) y métricas del modelo; con la semilla por defecto cumple los tres umbrales
make test     # tests de contrato con un Ollama simulado (no necesita GPU ni modelo)
```

- Dashboard: <http://localhost:8501> (pipeline, alumno, modelo, sesiones reales). API y `/docs`: <http://localhost:8010>.
- Las pantallas del terapeuta exigen `X-API-Key`; en compose la clave por defecto es `dev-terapeuta-local` (solo desarrollo; cámbiala en `environment/.env`).
- **Sin Ollama el stack arranca igual:** `GET /health` responde `degraded` (la BD está bien, el LLM no), y todo lo anterior funciona. Lo único que no funciona es **conversar en el chat** (`/chat/`), porque cada turno llama a un LLM.
- Windows sin make: `powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1 -SinModelo` (equivalente a `make up seed train` sin descargar el modelo) y `scripts\test-local.ps1` para los tests.
- `make reset` borra volúmenes y modelo para empezar de cero.

### Probar el chat con un LLM real (opcional)

El backend usa el Ollama del host (`OLLAMA_URL=http://host.docker.internal:11434`, modelo `qwen3:14b`, ~9 GB de descarga; con GPU de 16 GB va fluido).
`make pull-model` lo descarga. Se puede probar con otro modelo más pequeño cambiando `OLLAMA_MODEL` en `environment/.env`
(**no probado**: el prompt del evaluador 0/1/2 se afinó con `qwen3:14b`). **Sin GPU:** `make up-simulado` arranca el stack con `LLM_PROVIDER=simulado` (después `make seed` para tener alumnos y abre `/chat/`): la
valoración 0/1/2 la hace un LLM falso por reglas, sin modelo. Sirve para ejecutar y demostrar el prototipo; **no es el evaluador del producto**
(en el examen a ciegas acierta 21 de 26 respuestas buenas y da 1 falso 2 de 52 malas, pero falla con sinónimos que no conoce;
detalle y límites en [`docs/modo-simulado.md`](docs/modo-simulado.md)).

**Motor sustituible (API compatible con OpenAI).** Por defecto el backend usa la API nativa de Ollama (`LLM_PROVIDER=ollama`, necesaria para `think:false`). Con `LLM_PROVIDER=openai` habla con cualquier servidor compatible con OpenAI (`/v1/chat/completions`: el `/v1` de Ollama, vLLM, LM Studio, TabbyAPI…) configurado con `LLM_COMPAT_URL`, `LLM_COMPAT_MODEL` y `LLM_COMPAT_API_KEY`, sin cambiar nada más del sistema. Está probado con un servidor simulado en los tests y con un servidor real (Ollama 0.40.11 por su `/v1`, `qwen3:0.6b` en CPU: conversación completa con `make smoke`). Con qwen3 hace falta `LLM_COMPAT_REASONING_EFFORT=none` (el valor por defecto): sin él el razonamiento se come `max_tokens` y la respuesta llega cortada. También se probó por esta vía con `qwen3:14b` en la GPU (Ollama `/v1`, conversación completa) y el 26/10/2026 con TabbyAPI y otro modelo (`Qwen3-Coder-30B-A3B`): conversación completa y baterías 3 y 4. **No está probado con vLLM ni LM Studio.** El evaluador solo está validado con `qwen3:14b` por `ollama`: con el modelo de TabbyAPI la batería 3 dio un 12,2 % de falsos 2 (con `qwen3:14b`, 0 %), así que otro modelo obliga a remedirlo (`docs/api-conversacion.md`).

## Estructura

```
environment/   docker-compose.yml, Dockerfiles y .env.example
data/init-db/  migraciones SQL 001→013 (001 es histórica; la estructura vigente es la suma)
src/app/       backend FastAPI (routers/, guiones/guiones.json, static/chat/)
src/dashboard/ dashboard Streamlit (solo vía API, ADR-003)
src/generador/ src/ml/   corpus sintético y features antifuga (Marcos; ver src/generador/ORIGEN.md)
src/scripts/   seed_corpus, train_classifier, metricas_reales, bateria_valoracion, smoke_conversacion, mock_api_chat
src/tests/     pytest (contrato, ER v2, dashboard, límites, métricas, chat estático)
docs/          ER v2 (anotado, contrastado con el esquema real), arquitectura v2, ADR-001/002/003 (docs/adr/), contrato de las APIs,
               métricas reales, informe de validación, escalado a Kafka y Spark (solo diseño), informes de Marcos y réplica
scripts/       instalación y comprobación (setup-local.*, test-local.ps1, comprobar-stack.ps1)
```

Stack: Python 3.12 · FastAPI · SQLAlchemy · PostgreSQL 16 · scikit-learn · Streamlit · Docker Compose · Ollama (LLM local). Versiones exactas de todo (paquetes y sus dependencias indirectas en `src/constraints.txt`, imágenes con etiqueta y digest, modelos) y divergencias abiertas: [`docs/versiones.md`](docs/versiones.md).

## Decisiones de diseño relevantes

1. **ER v2:** una única `session_data` con `origen`; las reales exigen `conversacion_id`, las sintéticas `etiqueta_real_disenada`. El entrenamiento filtra `origen='sintetico'` (hay test anti-fuga).
2. **Intento por fila:** vista `turn_data` sobre `conversacion_turno`.
3. **Dashboard solo por API:** no abre Postgres ni lee ficheros del modelo.

Cada decisión tiene su ADR en [`docs/adr/`](docs/adr/): [ADR-001](docs/adr/ADR-001_session_data_unica_con_origen.md) (`session_data` única con `origen`), [ADR-002](docs/adr/ADR-002_turn_data_vista_sobre_intentos.md) (`turn_data` como vista) [ADR-003](docs/adr/ADR-003_dashboard_solo_por_api.md) (dashboard solo por API) y [ADR-004](docs/adr/ADR-004_puntuacion_012_solo_llm.md) (puntuación 0/1/2 solo con el LLM y su comprobación con respuestas etiquetadas). Arquitectura: [`docs/arquitectura_v2.mmd`](docs/arquitectura_v2.mmd) (imagen: [`.png`](docs/arquitectura_v2.png)); modelo de datos: [`docs/er_v2.mmd`](docs/er_v2.mmd).
