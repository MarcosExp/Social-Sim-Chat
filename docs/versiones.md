# Versiones del proyecto — lista de referencia

Última comprobación: **25/10/2026** (rama `chore/requirements-nf2`, PR n.º 5). Las tablas 2 a 4 las comprueba `src/tests/test_versiones.py`: si cambias una versión en un `requirements*.txt`, un Dockerfile o el compose y no la cambias aquí, el test falla. Las dependencias indirectas están fijadas en `src/constraints.txt` (apartado 8) y el mismo test comprueba que coincide con los `requirements*.txt` y con lo instalado.

**Regla.** Manda lo que fijan `src/requirements.txt`, `src/requirements-dev.txt`, `src/dashboard/requirements.txt`, `src/constraints.txt` y `environment/`. Este documento los refleja; no los sustituye. Cualquier cambio de versión se anota aquí, en la tabla de divergencias (apartado 7) si queda algo abierto, y en la memoria si mueve alguna cifra.

## 1. De dónde sale cada versión

| Fuente | Qué documenta | Dónde |
|---|---|---|
| NF2 (PDF, apartado 8 «Datos», criterio cuantitativo del clasificador) | scikit-learn 1.9.1, numpy 2.5.3, pandas 3.0.5 («versiones fijadas en el `requirements.txt` del repositorio»); con scikit-learn 1.6.1 el recall de estancamiento baja a 0,650 | `MarcosExp/Social-Sim-Chat`, `docs/NF2_Documentacion_y_Diseno_Tecnico.pdf` |
| `requirements.txt` del repo académico (Marcos, 13/10/2026, `9b9fbbb`) | numpy 2.5.3, pandas 3.0.5, pyyaml 6.0.3, scikit-learn 1.9.1 | raíz del repo académico |
| `src/requirements*.txt` y `environment/` de nf3 | todo lo demás (FastAPI, SQLAlchemy, Streamlit, imágenes…) | este repositorio |
| Llamada Álvaro–Marcos del 25/10/2026 (de palabra) | armonizar las cuatro versiones anteriores y pasar la imagen a Python 3.12 | PR n.º 5 |

El NF2 nombra las tecnologías (FastAPI, Ollama, scikit-learn, Streamlit, Plotly, Docker Compose, PostgreSQL) pero **solo da versión de tres: scikit-learn, numpy y pandas**. pyyaml 6.0.3 solo consta en el `requirements.txt` del repo académico. El resto de versiones no tiene otro respaldo documental que este repositorio.

## 2. Python y paquetes fijados (`==`)

| Paquete | Versión | Fichero | Origen | Requires-Python |
|---|---|---|---|---|
| fastapi | 0.115.6 | `src/requirements.txt` | heredada de Soultech (01/10/2026) | ≥ 3.8 |
| uvicorn | 0.34.0 | `src/requirements.txt` | heredada (extra `standard`) | ≥ 3.9 |
| sqlalchemy | 2.0.36 | `src/requirements.txt` | heredada | ≥ 3.7 |
| psycopg2-binary | 2.9.10 | `src/requirements.txt` | heredada | ≥ 3.8 |
| pydantic | 2.10.4 | `src/requirements.txt` | heredada | ≥ 3.8 |
| pydantic-settings | 2.7.1 | `src/requirements.txt` | heredada | ≥ 3.8 |
| httpx | 0.28.1 | `src/requirements.txt` y `src/dashboard/requirements.txt` | heredada | ≥ 3.8 |
| python-dotenv | 1.0.1 | `src/requirements.txt` | heredada | ≥ 3.8 |
| numpy | 2.5.3 | `src/requirements.txt` | **NF2** | **≥ 3.12** |
| pandas | 3.0.5 | `src/requirements.txt` y `src/dashboard/requirements.txt` | **NF2** | ≥ 3.11 |
| scikit-learn | 1.9.1 | `src/requirements.txt` | **NF2** | ≥ 3.11 |
| joblib | 1.4.2 | `src/requirements.txt` | heredada | ≥ 3.8 |
| pyyaml | 6.0.3 | `src/requirements.txt` | `requirements.txt` del repo académico (no consta en el texto del NF2) | ≥ 3.8 |
| pytest | 8.3.4 | `src/requirements-dev.txt` | heredada | ≥ 3.8 |
| streamlit | 1.56.0 | `src/dashboard/requirements.txt` | **PR n.º 5 (25/10/2026); no figura en el NF2** | ≥ 3.10 |
| plotly | 5.24.1 | `src/dashboard/requirements.txt` | heredada | ≥ 3.8 |
| tzdata | 2024.2 | `src/dashboard/requirements.txt` | heredada | ≥ 2 |

Las dependencias que no están en la tabla (47 paquetes indirectos: starlette, scipy, pyarrow…) se fijan en `src/constraints.txt`, no aquí (apartado 8).

**Python mínimo: 3.12** (lo impone numpy 2.5.3). Comprobado con 3.12.3 (local), 3.12.15 (imágenes Docker) y 3.13.16 (local): en los tres, los mismos tests y las mismas métricas del clasificador.

**Por qué streamlit 1.56.0.** pandas 3.0.5 no resuelve con ninguna versión de streamlit anterior (la 1.41.1 que teníamos, la 1.50.0, la 1.54.0 y la 1.55.0 dan `ResolutionImpossible`); la 1.56.0 es la primera que lo admite (`pandas<4`). La última publicada hoy es la 1.66.1; no se sube para no cambiar más de lo necesario. **Comprobado el 25/10/2026 con la 1.56.0:** se recorrieron las seis pestañas del dashboard con un navegador automatizado (backend en modo simulado, modelo entrenado, dos conversaciones): sin excepciones y con las cifras del modelo a la vista (F1-macro 0,797 · recall 0,725 · precisión 0,70). El registro de Streamlit avisaba de que `use_container_width` desaparece («se eliminará después del 31/12/2025») y de una tabla de tipos mezclados que Arrow no admite; esta PR cambia los 12 usos a `width="stretch"` y convierte esa tabla a texto, y el registro queda sin avisos. Visto bueno de Álvaro el 25/10/2026; **falta la conformidad de Marcos** (en la llamada solo se acordaron las cuatro del NF2).

## 3. Imágenes y servicios (`environment/`)

Cada imagen lleva **etiqueta exacta y digest** (`etiqueta@sha256:…`): la etiqueta se lee, el digest fija el contenido. Una etiqueta sola cambia cada vez que se reconstruye la imagen (por ejemplo, con las actualizaciones de seguridad de Debian). Los digest son los del índice multiarquitectura del registro de Docker Hub, comprobados el 25/10/2026.

| Pieza | Imagen fijada | Versión real (25/10/2026) | Fichero |
|---|---|---|---|
| Python (backend y dashboard) | `python:3.12.15-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704` | 3.12.15 sobre Debian 13 (trixie), pip 25.0.1 | `environment/Dockerfile.backend`, `Dockerfile.dashboard` |
| PostgreSQL | `postgres:16.15-alpine@sha256:f4610795587492cd4fb887c2dc3de301b813278bb6f616992061141b5f15ac36` | 16.15 | `environment/docker-compose.yml` |
| Ollama (perfil `ollama-local`) | `ollama/ollama:0.40.11@sha256:dea72d1e22270fe095b68fdf756d2b489d615643c5a2eaebbc5f569181e322d8` | 0.40.11 (la que se probó con nuestro cliente, apartado 4) | `environment/docker-compose.yml` |

**Cómo actualizar una imagen:** cambia la etiqueta y el digest a la vez, en el fichero y en esta tabla (el test lo comprueba), y repite `make up-simulado migrate seed train verify test smoke`. El digest se lee del registro (`docker pull <etiqueta>` y `docker image inspect <etiqueta> --format "{{index .RepoDigests 0}}"`).

**Extensiones de PostgreSQL: ninguna.** Las migraciones no ejecutan `CREATE EXTENSION`; usan `gen_random_uuid()`, que viene de serie desde PostgreSQL 13. Mínimo exigido por el esquema: 13; usado: 16.

**Frontend del chat** (`src/app/static/chat/`): HTML y JavaScript propios, sin bibliotecas externas ni CDN.

## 4. Modelos de lenguaje

| Modelo | Para qué | Dónde |
|---|---|---|
| `qwen3:14b` (Ollama) | evaluador 0/1/2 y variación de frase; el prompt se afinó con él; PC de Álvaro (RTX 5060 Ti 16 GB) | `environment/.env.example` (`OLLAMA_MODEL`, `LLM_COMPAT_MODEL`) |
| `gpt-oss:20b` | autor de la batería 3 (otra familia que el evaluador) | `src/tests/data/bateria_valoracion_3.json` |
| `qwen3:0.6b` | solo la prueba del protocolo `openai` del 25/10/2026 (CPU) | `README.md` y `docs/api-conversacion.md` (llegan con la PR n.º 4) |
| `simulado` (LLM falso por reglas) | modo sin GPU; versión del evaluador `simulado-2026-10-25+<hash>` | `src/app/simulado.py`, `docs/modo-simulado.md` (PR n.º 4) |
| Ollama 0.40.11 | servidor con el que se probaron los dos protocolos el 25/10/2026 (sandbox, sin GPU, `qwen3:0.6b`): `openai` (PR n.º 4) y la API nativa `ollama` (`think: false`, `keep_alive`, `num_ctx`, JSON schema del evaluador): conversación completa de 6 turnos con LLM y `/health` ok. El modelo de 0,6 B responde mal; solo se prueba el contrato del cliente | `README.md` y `docs/api-conversacion.md` (PR n.º 4); este apartado |

### El PC de las mediciones (Windows 11, RTX 5060 Ti)

Leído el 25/10/2026 de los ficheros del propio PC, en solo lectura. **Los registros del 12/10 ya no existen** (los más antiguos de Ollama son del 17/10), así que lo que cambia con el tiempo se da con la fecha de la fuente más cercana.

| Elemento | Valor | Fuente (fecha) | ¿Vale para el 12/10? |
|---|---|---|---|
| Equipo | Ryzen 7 5800X · 32 GB · RTX 5060 Ti 16 GB (15,9 GiB visibles, Blackwell, compute 12.0) · Windows 11 Pro, build 22631 | `C:\IA LOCAL\MANIFIESTO.md` (03/09); registro de Ollama (25/10) | Sí |
| `qwen3:14b` | manifiesto `sha256:8d6c98e1c8dbb1d0efa1522a150672d846a79c8f9b6b6e4309ab6a17c90dd038` (ID de `ollama list`: `8d6c98e1c8db`); GGUF `sha256:a8cc1361f3145dc01f6d77c6c82c9116b9ffe3c97b34716fe20418455876c40e`, 9.276.184.896 bytes, 14,8 B parámetros; **cuantización Q4_K_M** (`general.file_type = 15` en la cabecera del GGUF y `Q4_K_M` en el manifiesto) | `C:\Users\agarc\.ollama\models` (25/10): manifiesto escrito el 05/09/2026 01:45; el mismo ID consta en `C:\IA LOCAL\_publicar\d1-decision-bench\docs\METHOD.md` (09/10) | **Sí**: descargado antes del 12/10 y con el mismo ID el 09/10 |
| Ollama | 0.34.4 (09/10) → 0.40.3 (17/10) → 0.40.6 (desde el 18/10 a las 17:26; es la que corre hoy). **La actualización automática está activada** (`auto_update_enabled = 1`): la 0.40.11 está descargada y se instala sola al reiniciar la app (el primer paquete, bajado el 25/10 a las 11:14, no pasó la verificación de firma y se volvió a descargar a las 11:15) | `METHOD.md` (09/10); `server-5.log` (17/10); `upgrade.log` y `app.log` (18/10 y 25/10); ajustes de la app (25/10) | **No se sabe cuál**: el 12/10 estaba entre la 0.34.4 y la 0.40.3 |
| Opciones del servidor Ollama | contexto 131072, flash attention activada, caché KV `q4_0`, `keep alive` 5 min, un modelo cargado, una petición a la vez, escucha en 0.0.0.0:11434 | `server-5.log` (17/10) y `server.log` (25/10), iguales; ya estaban recomendadas en `C:\IA LOCAL\README.md` | Probable |
| Controlador NVIDIA | **617.42** el 25/10 a las 16:14 (`nvidia-smi`: KMD 617.42, CUDA 13.4); 617.14 el 09/10; 616.56 el 03/09 | captura de `nvidia-smi` de Álvaro (25/10); `METHOD.md`; `MANIFIESTO.md` | **No se sabe**: el 12/10 estaba entre las dos (617.14 el 09/10, 617.42 hoy) y no consta cuándo se actualizó. No se pudo leer el registro del controlador (acceso denegado al almacén de controladores) |
| Docker Desktop | 4.75.0 (227598), instalada el 02/06/2026; motor 29.5.2; Compose v5.1.3 y WSL2 2.7.12 (03/09, sin revalidar) | `AppData\Local\Docker\install-log.txt`; `electron-*.log` del 14/10 al 25/10; `MANIFIESTO.md` | **Sí**: misma versión desde el 02/06, sin actualizaciones registradas |

Lo que ya no se puede recuperar es la versión exacta de Ollama y la del controlador del 12/10 (**el controlador ha cambiado: 617.14 el 09/10, 617.42 hoy**; la lectura «probable 617.14» del primer análisis no se sostiene). Para que no vuelva a pasar, **cada medición con LLM real anota estas cuatro líneas** (apartado 9), al empezar y al acabar.

### Ollama 0.40.6 → 0.40.11: qué cambia y qué se comprobó

- **Notas de versión.** La 0.40.11 (24/10) trae síntesis de voz en macOS y los modelos `d3` (página oficial de la versión). Las 0.40.7 a 0.40.10 (18 al 23/10) añaden modelos (Flint, Nemotron, pplx-decider), voz, correcciones de la API *Responses* y de *Anthropic Messages* (que no usamos), los campos `renderer`, `parser` y `template_source` en `ollama show` y la API (solo se añaden) y **una actualización de llama.cpp en la 0.40.7**. Esas cuatro últimas, según un agregador de notas de versión (no se pudo abrir la página oficial de cada una); la 0.40.6 no se consultó. **Nada de lo que figura toca Windows, CUDA, la atención *flash*, la caché KV, `/api/chat`, `/v1/chat/completions` ni los esquemas JSON.** Lo único que puede mover velocidad o salida es la actualización de llama.cpp, y eso solo se ve con la GPU.
- **Contrato del cliente, comprobado el 25/10 contra la 0.40.11** (sin GPU, `qwen3:0.6b`): protocolo `openai` y API nativa `ollama` (apartado 4); en la nativa, el evaluador devolvió valoraciones con el esquema JSON (2, 0, 0, 2, 2).
- **No comprobado, solo medible en el PC:** latencia y salida con `qwen3:14b`, contexto de 131072, atención *flash* y caché KV `q4_0` en la RTX 5060 Ti.
- **Qué no cambió en las actualizaciones anteriores:** entre la 0.40.3 (17/10) y la 0.40.6 (18/10) el modelo (`qwen3:14b`, ID `8d6c98e1c8db`) y los ajustes del servidor (contexto, atención *flash*, caché KV) siguieron igual (`server-5.log` frente a `server.log`); no hay motivo para esperar otra cosa ahora, pero se anota con la versión nueva.
- **Procedimiento recomendado:** medir primero con la versión instalada (0.40.6), actualizar, repetir la prueba de humo y comparar (apartado 9); si no hay regresión, **fijar la 0.40.11 hasta después de la entrega** (desactivar la actualización automática) y medir todo lo demás con ella. Si hay regresión, reinstalar la 0.40.6. Mientras no se decida, no reiniciar la app de Ollama durante una medición: al reiniciar se instalaría sola la 0.40.11.

## 5. Herramientas con las que se ha verificado (no son dependencias)

| Herramienta | Versión |
|---|---|
| PostgreSQL de las pruebas locales | 16.15 (Ubuntu 24.04) |
| Docker / Docker Compose (sandbox de la auditoría) | 29.8.2 / v5.5.1 |
| Python local | 3.12.3 y 3.13.16 |
| pyflakes (criterio 5 de la rúbrica; no está en `requirements-dev.txt`) | 4.0.3 |
| Node / Mermaid CLI (diagramas) | 22.22.0 / 11.16.0 |

## 6. Cifras que dependen de las versiones

El clasificador es un RandomForest: scikit-learn 1.9.1 y 1.6.1 reparten distinto. El corpus es idéntico con las dos.

| Medición | scikit-learn | F1-macro | Recall estancamiento | Precisión estancamiento |
|---|---|---|---|---|
| NF2: media de 10 semillas (Marcos) | 1.9.1 | 0,78 ± 0,02 | 0,69 ± 0,05 | 0,69 ± 0,05 |
| NF2: misma medición | 1.6.1 | 0,78 (sin cambio) | 0,650 (0,6497 en la medición de Marcos) | no indicada en el NF2 |
| nf3, semilla 42 (informe del 12/10/2026) | 1.6.1 | 0,793 | 0,670 | 0,741 |
| nf3, semilla 42 (25/10/2026, PR n.º 5) | 1.9.1 | **0,797** | **0,725** | **0,70** |
| nf3, 10 semillas, `ml/evaluar_corpus.py` de Marcos (25/10/2026) | 1.9.1 (numpy 2.5.3, pandas 3.0.5) | 0,78 ± 0,02 | 0,69 ± 0,05 | 0,69 ± 0,05 |
| nf3, 10 semillas, misma orden y mismo corpus (25/10/2026) | 1.6.1 (numpy 2.2.1, pandas 2.2.3) | 0,78 ± 0,03 | 0,65 ± 0,05 | 0,72 ± 0,04 |

**Con las versiones fijadas, la medición de 10 semillas de nf3 reproduce las cifras del NF2** (0,78 ± 0,02 · 0,69 ± 0,05 · 0,69 ± 0,05); con las antiguas, el recall medio queda en 0,65 y no cumple el umbral (60 % de las semillas). Con las nuevas, la media cumple los tres umbrales; por semilla, el F1-macro lo cumple el 70 %, la precisión el 80 % y el recall el 80 %: la memoria no debe decir «en todas las semillas». Se repite con `cd src && python ml/evaluar_corpus.py --config generador/config.yaml --semillas 10` (unos 3 minutos).

**Qué depende de estas versiones y qué no.** Dependen: el clasificador (sus cifras y el modelo guardado), nada más. No dependen: las baterías del evaluador 0/1/2 (dependen del LLM y de los *prompts*), el modo simulado (reglas), los controles de seguridad ni los tests (239 en la integración, en verde con las dos pilas). El dashboard cambia de streamlit 1.41.1 a 1.56.0 (ver apartado 2).

Umbrales: F1-macro ≥ 0,75; recall y precisión de estancamiento ≥ 0,65. Las cifras del informe de validación, de ADR-001 y de `src/generador/ORIGEN.md` son mediciones fechadas con la pila anterior y se dejan como estaban. **La memoria debe citar las de scikit-learn 1.9.1.** Tras cambiar de versión hay que reentrenar (`make train`): el modelo guardado (`src/models/`, no versionado) es un fichero joblib que scikit-learn avisa de que no debe cargarse con otra versión.

## 7. Divergencias y su estado

| Id | Divergencia | Estado |
|---|---|---|
| D-01 | nf3 (`main`, PR n.º 1–4) y las tres ramas de Soultech usan numpy 2.2.1, pandas 2.2.3, scikit-learn 1.6.1, pyyaml 6.0.2 y Python 3.11; el NF2 documenta las versiones del apartado 2 | nf3: se resuelve al fusionar la PR n.º 5. **Soultech: se deja como está hasta después de la entrega (decisión del 25/10/2026)**; al unificar, se copian `requirements*.txt` y `constraints.txt` de nf3 y se reentrena (el modelo guardado no sirve entre versiones de scikit-learn) |
| D-02 | streamlit 1.41.1 → 1.56.0: no figura en el NF2; es consecuencia de pandas 3 | Visto bueno de Álvaro el 25/10/2026; falta la conformidad de Marcos (revisión de la PR n.º 5) |
| D-03 | README del repo académico: «Python 3.11 o superior; probado con 3.13», pero numpy 2.5.3 exige 3.12 | Abierta (repo de Marcos) |
| D-04 | README del repo académico cita `environment/requirements.txt`; el fichero está en la raíz (`environment/` solo tiene `.gitkeep`) | Abierta (repo de Marcos) |
| D-05 | El NF2 promete «Docker Compose con versiones fijadas», pero `ollama/ollama:latest` no estaba fijada y `postgres:16-alpine` y `python:3.12-slim` fijaban solo la versión mayor | **Cerrada el 25/10/2026**: etiqueta exacta y digest en las tres imágenes (apartado 3) |
| D-06 | Solo se fijaban las dependencias directas; las transitivas las resolvía pip al construir | **Cerrada el 25/10/2026**: `src/constraints.txt` (apartado 8). Se vio un caso real: sin él, el dashboard montaba numpy 2.5.4 y tzdata 2024.2, y el backend numpy 2.5.3 y tzdata 2026.5 |
| D-07 | Cifras del clasificador del 12/10/2026 medidas con scikit-learn 1.6.1 (apartado 6) | Documentada; la memoria cita las nuevas |
| D-08 | Versiones de Ollama, `qwen3:14b`, Docker Desktop y controlador NVIDIA del PC de Álvaro sin anotar | Cerrada el 25/10/2026 (apartado 4) salvo dos datos irrecuperables del 12/10: la versión exacta de Ollama y la del controlador (hoy 617.42; el 09/10, 617.14) |
| D-09 | `.env.example` nombra `TABBYAPI_MODEL=Qwen3.8-27B-EXL3-3.0bpw` (perfil opcional de TabbyAPI) | Declarado en el repositorio, no comprobado |
| D-10 | La actualización automática de Ollama en el PC de Álvaro puede cambiar la versión en mitad de una medición (0.40.11 ya descargada) | Abierta: decidir antes de la medición si se actualiza y se fija (apartado 4) |

## 8. Dependencias indirectas: `src/constraints.txt`

Fija **todas** las versiones (64 paquetes: los 17 de la tabla del apartado 2 y 47 indirectos) y se aplica con `pip install -r … -c constraints.txt` en las dos imágenes, en `make test` y en `scripts\test-local.ps1`. Un solo fichero para las dos imágenes, para que un paquete compartido tenga la misma versión en las dos (con ficheros sueltos, el dashboard montaba numpy 2.5.4 y tzdata 2024.2 frente a numpy 2.5.3 y tzdata 2026.5 del backend).

Generado el 25/10/2026 en Python 3.12.3 (Linux x86-64), sin conflictos (`pip check`). Los paquetes que solo existen en Windows (por ejemplo `colorama`) no figuran y los resuelve pip; el contenedor siempre es Linux, así que las imágenes son idénticas en cualquier equipo.

**Para cambiar una versión** (directa o indirecta): cámbiala en el `requirements*.txt` si es directa, regenera el fichero con el entorno nuevo del apartado 9, repite `make up-simulado migrate seed train verify test smoke`, actualiza la tabla del apartado 2 y, si se mueve alguna cifra, el apartado 6. `src/tests/test_versiones.py` comprueba que `constraints.txt` contiene cada paquete directo con su versión, que todo está fijado con `==` y que lo instalado coincide.

## 9. Cómo volver a comprobarlo

```bash
cd src && python -m pytest tests/test_versiones.py          # esta lista frente a requirements*.txt, Dockerfile y compose
python -m pip install -r requirements-dev.txt -r dashboard/requirements.txt -c constraints.txt && python -m pip check
docker compose -f ../environment/docker-compose.yml --env-file ../environment/.env exec backend \
  python -c "import sys,numpy,pandas,sklearn,yaml;print(sys.version.split()[0],numpy.__version__,pandas.__version__,sklearn.__version__,yaml.__version__)"
docker compose -f ../environment/docker-compose.yml --env-file ../environment/.env exec db postgres --version
```

Regenerar `src/constraints.txt` (solo si se decide cambiar versiones; ver apartado 8):

```bash
python3.12 -m venv /tmp/v && /tmp/v/bin/pip install -r requirements-dev.txt -r dashboard/requirements.txt && /tmp/v/bin/pip check && /tmp/v/bin/pip freeze
```

Al actualizar Ollama en el PC (0.40.6 → 0.40.11), una sola vez y en este orden; las dos salidas se pegan en el informe de la medición:

```powershell
ollama --version; scripts\test-local.ps1 -Humo      # 1. con la versión instalada (línea de base)
# 2. actualizar Ollama (la app ya tiene descargada la 0.40.11) y volver a abrirla
ollama --version; scripts\test-local.ps1 -Humo      # 3. con la nueva; comparar mediana, máximo y primer turno
```

Criterio: sin errores y con la mediana en caliente en el orden de la del 12/10 (0,94 s; máximo 1,23 s; primer turno en frío 7,2 s). Si no se cumple, reinstalar la 0.40.6 y anotarlo.

En el PC, antes de cada medición con el LLM real (PowerShell), y se copian los resultados al informe de esa medición:

```powershell
ollama --version                                                    # versión de Ollama
ollama list | Select-String "qwen3:14b"                             # ID del modelo (8d6c98e1c8db)
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader    # controlador NVIDIA
docker version --format "Docker Desktop: {{.Server.Platform.Name}} · motor {{.Server.Version}}"
```
