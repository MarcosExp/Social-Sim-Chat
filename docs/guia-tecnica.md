# Guía técnica

Para quien mantenga o amplíe el código. Qué hace el sistema para quien lo usa: [`guia-usuario.md`](guia-usuario.md). Cómo arrancarlo: [`README.md`](../README.md). Cómo se trabaja con ramas y entregas: [`CONTRIBUIR.md`](../CONTRIBUIR.md). Autoría y procedencia: [`AUTORIA.md`](../AUTORIA.md).

## 1. Visión general

Cuatro piezas que solo se hablan por API. Diagrama fuente: [`arquitectura_v2.mmd`](arquitectura_v2.mmd); modelo de datos: [`er_v2.mmd`](er_v2.mmd).

| Pieza | Tecnología | Dónde |
|---|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2 | `src/app/` |
| Base de datos | PostgreSQL 16 | `data/init-db/` (migraciones) |
| Chat del menor | HTML, JS y CSS estáticos, sin compilar; lo sirve el backend en `/chat/` | `src/app/static/chat/` |
| Dashboard del terapeuta | Streamlit + Plotly; **solo habla con la API** (ADR-003) | `src/dashboard/` |
| Evaluador y personaje | LLM local por Ollama (`qwen3:14b`), API compatible con OpenAI o modo simulado | `src/app/llm_client.py`, `src/app/simulado.py` |
| Clasificador | scikit-learn (RandomForest), entrenamiento offline por lotes | `src/scripts/train_classifier.py`, `src/ml/` |
| Generador de corpus | De Marcos; carga la base por lotes | `src/generador/` |

## 2. Requisitos y entorno

- **Para ejecutar:** Docker con Compose v2; `make` en Linux, macOS o WSL. Sin `make` en Windows: `scripts\setup-local.ps1` y `scripts\comprobar-stack.ps1`.
- **Para el modelo real:** Ollama en el equipo (escuchando en `0.0.0.0:11434`) con `qwen3:14b` (`make pull-model`); GPU de 16 GB probada.
- **Para desarrollar fuera de Docker:** Python 3.12 (numpy 2.5.3 lo exige) y un PostgreSQL con las migraciones aplicadas.
- **Versiones:** todo está fijado. Paquetes directos en los `requirements*.txt`, indirectos en `src/constraints.txt`, imágenes con etiqueta y *digest* en `environment/`. Lista y divergencias abiertas: [`versiones.md`](versiones.md).
- **Configuración:** variables en `environment/.env` (plantilla comentada en `environment/.env.example`). `make up` lo crea si falta y genera la clave del terapeuta (`scripts/preparar-env.sh`). Los parámetros que importan:

| Variable | Efecto |
|---|---|
| `API_KEY_TERAPEUTA` | Clave de las rutas del terapeuta. Sin valor por defecto; con `ENV` distinto de `development` el backend no arranca si está vacía o es la antigua `dev-terapeuta-local` |
| `LLM_PROVIDER` | `ollama` (por defecto, validado), `openai` (cualquier servidor compatible; solo `qwen3:14b` por `ollama` está validado como evaluador), `tabbyapi` (alias histórico) o `simulado` (sin GPU; no es el evaluador del producto) |
| `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_NUM_CTX`, `LLM_KEEP_ALIVE`, `OLLAMA_TIMEOUT_S` | Conexión y comportamiento con Ollama |
| `LLM_COMPAT_*` | Servidor compatible con OpenAI (URL sin `/v1`, modelo, clave, formato de respuesta, `reasoning_effort`) |
| `LLM_PRECALENTAR` | `true` precalienta el modelo al arrancar; `/health` lo informa en `llm_precalentamiento` |
| `MAX_SESIONES_SEMANA` | Límite de conversaciones reales por alumno en 7 días; `0` lo apaga |
| `SIMULADO_REGISTRA_SESIONES` | Con `simulado`, si sus conversaciones generan sesión real (por defecto no) |

## 3. Estructura del código

```
environment/    docker-compose.yml, Dockerfiles, .env.example
data/init-db/   migraciones SQL 001→013 (idempotentes; la estructura vigente es la suma)
src/app/        backend FastAPI
  main.py         arranque (lifespan: comprobación de configuración y precalentamiento), routers, manejadores de error
  config.py       variables de entorno (pydantic-settings)
  seguridad.py    clave del terapeuta y comprobación de configuración
  errores.py      formato único de error {codigo, mensaje, reintentable}
  conversacion.py guion, valoración y flujo de cada turno
  guarda.py       guarda de inyecciones (antes del LLM)
  llm_client.py   cliente Ollama / compatible con OpenAI y precalentamiento
  simulado.py     LLM falso por reglas
  metricas.py     cinco métricas por sesión (DEFINICION_VERSION)
  ml_config.py    adaptador a `src/ml/` (de Marcos, sin modificar); config del modelo de servicio sin %DET
  prediccion.py   carga de classifier.joblib y predicción sobre sesiones reales (orientativa)
  models.py, schemas.py, db.py   ORM, contratos y sesión de base de datos
  routers/        students, sessions, conversaciones, correcciones, predicciones, modelo, resumen, health
  guiones/guiones.json   guion literal, personajes y competencias
  static/chat/    el chat del menor
src/dashboard/  app.py (seis pestañas) y cliente_api.py (único acceso a datos)
src/generador/, src/ml/   de Marcos; ver src/generador/ORIGEN.md (no modificar sin acordarlo)
src/scripts/    seed_corpus, train_classifier, resumen_modelo, metricas_reales, bateria_valoracion, smoke_conversacion, generar_turnos…
src/tests/      pytest
docs/           ADR, contratos de las APIs, métricas, validación, versiones, guías
scripts/        instalación y comprobación (Linux/macOS/WSL y Windows)
```

## 4. Qué pasa en un turno

Código en `conversacion.py::responder`:

1. El chat envía `POST /conversaciones/{id}/turnos` con el texto del menor (la latencia se mide en el servidor desde el último mensaje del personaje).
2. **Apertura** (nodos `a1`, `a2`, `a2A`, `a3`): ramas por reglas, sin LLM.
3. **Turno de competencia:** `guarda.detectar_inyeccion` primero; si salta, valoración 0 sin llamar al LLM (`evaluacion_origen = guarda_inyeccion`). Si no, **una sola llamada** al LLM que devuelve `{análisis, evaluación 0|1|2, reacción}` (el texto del menor va entre comillas triples; el prompt es `PROMPT_EVALUADOR`).
4. **Decisión del guion:** si la valoración es menor que 2 y es el primer intento, el personaje da la ayuda del guion y hay un segundo intento (máximo 2). Si no, se avanza; tras la última figura la conversación termina.
5. Se guarda una fila por mensaje en `conversacion_turno` (menor y personaje), con `evaluacion`, `evaluacion_origen`, `evaluador_version`, `latencia_ms` y `llm_ms`.
6. Al terminar, `metricas.registrar_sesion` crea la fila de `session_data` con `origen = 'real'`. Si falla, no rompe la conversación y `scripts.metricas_reales` las recalcula.

- Un cerrojo por conversación evita turnos simultáneos; el cliente LLM atiende una petición a la vez.
- Los errores salen siempre como `{codigo, mensaje, reintentable}`; tabla en [`api-conversacion.md`](api-conversacion.md). La validación (422), la base de datos caída (503, con `Retry-After`) y los errores internos (500, sin detalles) los gestiona `errores.py`.

## 5. Datos y migraciones

- **Modelo ER v2** ([`adr/ADR-001`](adr/ADR-001_session_data_unica_con_origen.md)): una sola tabla `session_data` con `origen` (`real` / `sintetico`). Las reales exigen `conversacion_id`; las sintéticas, `etiqueta_real_disenada`.
- **`turn_data`** es una **vista** sobre `conversacion_turno` (una fila por figura, regla 2/1/0; [`adr/ADR-002`](adr/ADR-002_turn_data_vista_sobre_intentos.md)). Vocabulario figura / nodo / turno / intento: tabla en [`api-conversacion.md`](api-conversacion.md).
- **Correcciones del terapeuta:** `correccion_log` guarda autor declarado, valor anterior y nuevo; el valor efectivo es `COALESCE(accuracy_corregido, accuracy_score)`.
- **Añadir una migración:**
  1. Crea `data/init-db/0NN_nombre.sql` con el número siguiente.
  2. Hazla idempotente; no reescribas las anteriores.
  3. Aplícala a un volumen existente con `make migrate`.
  4. `tests/test_migraciones.py` las reaplica todas: debe seguir en verde.
- Respeta los finales de línea (`001_schema.sql` y los `.ps1` son CRLF).

## 6. Trazabilidad y versiones

| Qué | Dónde | Cuándo cambia |
|---|---|---|
| `evaluador_version` | cada turno valorado | Etiqueta legible (`EVALUADOR_ETIQUETA`, hoy `2026-10-12-p3`) más un hash del prompt, el criterio, el esquema, la temperatura y la guarda: cambia sola al tocar cualquiera |
| `definicion_version` | cada sesión | Al cambiar una fórmula de `metricas.py`: sube `DEFINICION_VERSION` y recalcula con `scripts.metricas_reales` |
| `modelo_version` | cada predicción | Al reentrenar |
| Versión del guion | `guiones.json` | A mano; el texto de figuras y ayudas es literal y se cambia aquí, no en el código |

## 7. Clasificador y pipeline offline

- `make seed` carga el corpus del generador (100 alumnos, 1.500 sesiones) y los turnos sintéticos; `make train` entrena y escribe `src/models/classifier.joblib`, `metrics.json` y las predicciones en `session_data`; `make verify` muestra los conteos y las métricas.
- **Control anti-fuga:** el entrenamiento solo lee `origen = 'sintetico'`, con validación cruzada agrupada por alumno, un modelo señuelo y etiquetas permutadas. Hay prueba que lo comprueba.
- **Criterios:** `train_classifier.py` importa los nueve de `UMBRALES` de `src/ml/evaluar_corpus.py` (código de Marcos, sin modificar) y los guarda en `metrics.json`; `make verify` imprime «criterios k/9».
- **Dos modelos en un mismo `classifier.joblib`.** El **evaluado** (15 features, con %DET) da las métricas y las predicciones del corpus sintético por validación cruzada. El **de servicio** (clave `servicio`, 12 features, **sin %DET**, `modelo_version` con `sinDET`) se entrena con las mismas sesiones y los mismos folds y es el que usa el backend sobre sesiones reales. Su configuración sale de `app/ml_config.py` (`config_servicio()`: la config del generador sin las métricas de `metricas.PROVISIONALES`); `ml/` no se toca.
- **Predicción sobre sesiones reales (`app/prediccion.py`).** Se carga el joblib al arrancar y se relee si el fichero cambia (`make train` con el backend en marcha); si falta o no encaja, la API sigue y `/health` lo dice (`clasificador`). Al cerrar una sesión real y al corregir un turno se recalculan las predicciones del alumno (`classifier_predictions` + última en `session_data`). Las features son de ventana: hacen falta 4 sesiones reales en una misma competencia, las 3 primeras no se predicen y la alerta (3 no-progreso seguidos) usa las predicciones anteriores. Solo entran sesiones `origen='real'`. La prueba `test_prediccion_real.py` comprueba que el joblib guarda la misma lista de features que construye la inferencia.
- **Límite:** entrenado con datos sintéticos; las escalas reales pueden no coincidir (`fuera_de_rango` lo señala) y no está validado con menores reales. `aMLU`, `PEPE` e `IRC` dependen del evaluador 0/1/2, aún sin validar.
- No hay reentrenamiento automático.
- Escalado a Kafka y Spark: [`escalado.md`](escalado.md) (solo diseño, no implementado).

## 8. Pruebas

- **En el contenedor:** `make test` (instala pytest la primera vez).
- **Fuera de Docker:**
  1. `cd src && pip install -r requirements-dev.txt -c constraints.txt`
  2. Aplica `data/init-db/*.sql` a un PostgreSQL de pruebas.
  3. Exporta `TEST_DATABASE_URL` con la cadena de conexión de esa base (tiene prioridad sobre `DATABASE_URL`).
  4. `python -m pytest`
- **Sin base de datos** las pruebas que la necesitan se saltan en vez de fallar.
- `test_versiones.py` exige que lo instalado coincida con `constraints.txt` y que las tablas de `versiones.md` estén al día.
- Las pruebas usan un Ollama simulado (`tests/fake_ollama.py`). Contra el LLM real:
  - `make smoke`: conversación completa con latencia por turno.
  - `make bateria`: regresión del evaluador con respuestas etiquetadas.
  - `pytest -m humo`: pruebas de humo contra el Ollama real.
- El recuento de pruebas lo da `pytest`; no se copia en los documentos.

## 9. Tareas habituales

| Quiero… | Hago… |
|---|---|
| Cambiar el prompt o el criterio del evaluador | Edita `PROMPT_EVALUADOR` y `EVALUADOR_ETIQUETA` en `conversacion.py`; **remide con `make bateria`** (objetivos: ≥ 82 % de buenas con 2 y ≤ 5 % de falsos 2 en la batería 3); anota la medición en [`informe-validacion-metricas-reales.md`](informe-validacion-metricas-reales.md) |
| Usar otro modelo o servidor | `LLM_PROVIDER` y variables `LLM_COMPAT_*`; el evaluador solo está validado con `qwen3:14b` por `ollama`, así que hay que remedir ([`api-conversacion.md`](api-conversacion.md)) |
| Cambiar una fórmula de métrica | `metricas.py` y `DEFINICION_VERSION`; actualiza [`metricas-reales.md`](metricas-reales.md) y recalcula |
| Cambiar una versión de paquete o imagen | Edita el `requirements*.txt` o `environment/`, `constraints.txt` y [`versiones.md`](versiones.md); `test_versiones.py` falla si falta algo |
| Añadir un endpoint | Router en `src/app/routers/`, contrato en `schemas.py`, tests y documentación en [`api-dashboard.md`](api-dashboard.md) o [`api-conversacion.md`](api-conversacion.md); si el dashboard lo necesita, solo por `cliente_api.py` |
| Tomar una decisión de diseño | Un ADR nuevo en `docs/adr/` (los cuatro vigentes: sesión única con origen, vista `turn_data`, dashboard solo por API, puntuación solo por LLM) |
| Cambiar el chat | `src/app/static/chat/`; `tests/test_chat_estatico.py` comprueba contraste, marcas de accesibilidad y mensajes de error |

## 10. Diagnóstico

- `make health` y `GET /health`: `status` es `ok` o `degraded` (la base de datos va bien y el LLM no); informa de `auth_terapeuta`, `llm_provider`, `llm`, `llm_model`, `llm_modelo_disponible` y `llm_precalentamiento`.
- `make logs`: registro estándar de Uvicorn y de los módulos. **No hay recogida centralizada ni alertas.**
- Fallos frecuentes:
  - **Compose no arranca:** falta `API_KEY_TERAPEUTA`. Usa `make up` (la genera) o defínela en `environment/.env`.
  - **`/health` con `llm` distinto de `ok`:** Ollama no llega. Comprueba que escucha en `0.0.0.0` y que el contenedor alcanza `host.docker.internal`; si falta el modelo, `make pull-model`.
  - **Esquema desactualizado en un volumen existente:** `make migrate`.
  - **Empezar de cero:** `make reset` (borra volúmenes y modelo).
- La puerta del backend es la 8010 y la del dashboard la 8501 (`BACKEND_PORT`, `DASHBOARD_PORT`).

## 11. Seguridad y límites que conviene recordar

- Una clave compartida; el nombre del terapeuta que corrige (`X-Terapeuta`) se declara y no se verifica.
- La nota clínica no está cifrada; no hay cifrado en reposo.
- El chat del menor no tiene autenticación: el alumno se identifica por su `student_id`.
- La guarda de inyecciones cubre 7 patrones y reconoce 6 de las 26 redacciones del examen: es una defensa adicional, no un cierre.
- No hay filtro de contenido sobre la «reacción» del LLM.
- Que el LLM sea local depende de la configuración: con `LLM_PROVIDER=openai` apuntando a un servicio externo, los textos del menor viajan a él.
- Los datos son sintéticos y el evaluador no está validado con conversaciones reales.

Lista completa en el [`README.md`](../README.md), apartado «Diseñado pero NO implementado».
