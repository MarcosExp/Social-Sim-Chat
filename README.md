# SOCIAL-SIM Chat — prototipo para la entrega NF3 (Grupo 12)

Entrenador conversacional y *learning analytics* para menores con TEA / síndrome de Asperger (6-12 años).
Módulo C088 · Curso de Especialización en IA y Big Data (iFP) · Grupo 12: Álvaro García Puche y Marcos Expósito Flox.

> **Prototipo académico, sin validez clínica.** Los datos del clasificador son sintéticos; las sesiones «reales» son
> conversaciones de prueba. Estado del repositorio: **privado, sin licencia** (todos los derechos reservados) hasta que
> el equipo decida cómo publicarlo; ver [`AUTORIA.md`](AUTORIA.md).

## Qué hay aquí (implementado y probado)

| Pieza | Dónde | Estado |
|---|---|---|
| Base de datos PostgreSQL 16, migraciones 001→011 | `data/init-db/` | Implementada. ER v2: una sola tabla `session_data` con `origen` (`sintetico`/`real`) |
| Backend FastAPI (alumnos, sesiones, conversación, correcciones, modelo, predicciones, resumen) | `src/app/` | Implementado. Contrato: [`docs/api-dashboard.md`](docs/api-dashboard.md), [`docs/api-conversacion.md`](docs/api-conversacion.md) |
| Chat del menor (HTML estático servido por el backend) | `src/app/static/chat/` → `http://localhost:8010/chat/` | Implementado; **necesita un LLM** (Ollama) para responder |
| Dashboard del terapeuta (Streamlit, solo habla con la API) | `src/dashboard/` → `http://localhost:8501` | Implementado |
| Generador de corpus sintético y evaluación antifuga | `src/generador/`, `src/ml/` | De Marcos, sin modificar |
| Clasificador (RandomForest, CV por alumno, anti-fuga) | `src/scripts/train_classifier.py` | Implementado; entrena offline y escribe la predicción en `session_data` |
| Vista `turn_data` (una fila por figura, regla 2/1/0) | migración 009 | Implementada (solo conversaciones reales) |
| Tests (158) | `src/tests/` | Pasan; usan un Ollama simulado (`tests/fake_ollama.py`) |

## Diseñado pero NO implementado (límites conocidos)

- **Turnos sintéticos:** `generar_turnos.py` no existe; el corpus sintético no tiene turnos y la vista `turn_data` solo cubre conversaciones reales.
- **Predicción sobre sesiones reales:** no se hace. `GET /students/{id}/prediccion` devuelve `disponible:false` con los motivos (hacen falta 4 sesiones reales, `pct_DET` es provisional, el evaluador del 0/1/2 no está validado).
- **Autenticación:** una clave compartida (`X-API-Key`) y un nombre de autor (`X-Terapeuta`) sin verificar. No hay usuarios ni roles.
- **Silencios** del menor no se registran; la **nota clínica no está cifrada**; no hay predicción en línea.
- El evaluador 0/1/2 (LLM) se validó con baterías propias, no con conversaciones reales anotadas: [`docs/informe-validacion-metricas-reales.md`](docs/informe-validacion-metricas-reales.md).
- Las fórmulas de las métricas reales son una propuesta explícita y revisable: [`docs/metricas-reales.md`](docs/metricas-reales.md).

## Arrancarlo sin GPU (solo con este README)

Requisitos: Docker (con Compose v2). Linux/macOS/WSL: `make`. Windows sin make: ver más abajo.

```bash
git clone https://github.com/cCoolBoox/social-sim-chat-nf3 && cd social-sim-chat-nf3
make up       # crea environment/.env si falta, construye y levanta Postgres + backend + dashboard
make seed     # genera el corpus sintético (100 alumnos, 1500 sesiones) y lo carga en Postgres
make train    # entrena el clasificador y escribe las predicciones (~30 s)
make verify   # conteos en BD y estado del modelo: debe salir 100 / 1500 / 1200 y «cumple» según métricas
make test     # 158 tests de contrato con un Ollama simulado (no necesita GPU ni modelo)
```

- Dashboard: <http://localhost:8501> (pipeline, alumno, modelo, sesiones reales). API y `/docs`: <http://localhost:8010>.
- Las pantallas del terapeuta exigen `X-API-Key`; en compose la clave por defecto es `dev-terapeuta-local` (solo desarrollo; cámbiala en `environment/.env`).
- **Sin Ollama el stack arranca igual:** `GET /health` responde `degraded` (la BD está bien, el LLM no), y todo lo anterior funciona. Lo único que no funciona es **conversar en el chat** (`/chat/`), porque cada turno llama a un LLM.
- Windows sin make: `powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1 -SinModelo` (equivalente a `make up seed train` sin descargar el modelo) y `scripts\test-local.ps1` para los tests.
- `make reset` borra volúmenes y modelo para empezar de cero.

### Probar el chat con un LLM real (opcional)

El backend usa el Ollama del host (`OLLAMA_URL=http://host.docker.internal:11434`, modelo `qwen3:14b`, ~5 GB; con GPU de 16 GB va fluido).
`make pull-model` lo descarga. Se puede probar con otro modelo más pequeño cambiando `OLLAMA_MODEL` en `environment/.env`
(**no probado**: el prompt del evaluador 0/1/2 se afinó con `qwen3:14b`). Tampoco hay todavía un modo «LLM simulado» ejecutable
en el stack (solo en los tests): está pendiente de decidir quién lo hace.

## Estructura

```
environment/   docker-compose.yml, Dockerfiles y .env.example
data/init-db/  migraciones SQL 001→011 (001 es histórica; la estructura vigente es la suma)
src/app/       backend FastAPI (routers/, guiones/guiones.json, static/chat/)
src/dashboard/ dashboard Streamlit (solo vía API, ADR-003)
src/generador/ src/ml/   corpus sintético y features antifuga (Marcos; ver src/generador/ORIGEN.md)
src/scripts/   seed_corpus, train_classifier, metricas_reales, bateria_valoracion, smoke_conversacion, mock_api_chat
src/tests/     pytest (contrato, ER v2, dashboard, límites, métricas, chat estático)
docs/          contrato de las APIs, métricas reales, informe de validación, informes de Marcos y réplica
scripts/       instalación y comprobación (setup-local.*, test-local.ps1, comprobar-stack.ps1)
```

Stack: Python 3.11 · FastAPI · SQLAlchemy · PostgreSQL 16 · scikit-learn · Streamlit · Docker Compose · Ollama (LLM local).

## Decisiones de diseño relevantes

1. **ER v2:** una única `session_data` con `origen`; las reales exigen `conversacion_id`, las sintéticas `etiqueta_real_disenada`. El entrenamiento filtra `origen='sintetico'` (hay test anti-fuga).
2. **Intento por fila:** vista `turn_data` sobre `conversacion_turno`.
3. **Dashboard solo por API:** no abre Postgres ni lee ficheros del modelo.
