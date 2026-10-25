# Versiones del proyecto — lista de referencia

Última comprobación: **25/10/2026** (rama `chore/requirements-nf2`, PR n.º 5). Las tablas 2 a 4 las comprueba `src/tests/test_versiones.py`: si cambias una versión en un `requirements*.txt`, un Dockerfile o el compose y no la cambias aquí, el test falla.

**Regla.** Manda lo que fijan `src/requirements.txt`, `src/requirements-dev.txt`, `src/dashboard/requirements.txt` y `environment/`. Este documento los refleja; no los sustituye. Cualquier cambio de versión se anota aquí, en la tabla de divergencias (apartado 7) si queda algo abierto, y en la memoria si mueve alguna cifra.

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

**Python mínimo: 3.12** (lo impone numpy 2.5.3). Comprobado con 3.12.3 (local), 3.12.15 (imágenes Docker) y 3.13.16 (local): en los tres, los mismos tests y las mismas métricas del clasificador.

**Por qué streamlit 1.56.0.** pandas 3.0.5 no resuelve con ninguna versión de streamlit anterior (la 1.41.1 que teníamos, la 1.50.0, la 1.54.0 y la 1.55.0 dan `ResolutionImpossible`); la 1.56.0 es la primera que lo admite (`pandas<4`). La última publicada hoy es la 1.66.1; no se sube para no cambiar más de lo necesario. **Pendiente de confirmar con Marcos** (en la llamada solo se acordaron las cuatro del NF2).

## 3. Imágenes y servicios (`environment/`)

| Pieza | Etiqueta fijada | Versión real al construir (25/10/2026) | Fichero |
|---|---|---|---|
| Python (backend y dashboard) | `python:3.12-slim` | 3.12.15 sobre Debian 13 (trixie), pip 25.0.1 | `environment/Dockerfile.backend`, `Dockerfile.dashboard` |
| PostgreSQL | `postgres:16-alpine` | 16.15 | `environment/docker-compose.yml` |
| Ollama (perfil `ollama-local`) | `ollama/ollama:latest` | **sin fijar** | `environment/docker-compose.yml` |

Las etiquetas fijan la versión mayor, no la exacta: la versión real cambia al descargar una imagen nueva. Ver D-05.

**Extensiones de PostgreSQL: ninguna.** Las migraciones no ejecutan `CREATE EXTENSION`; usan `gen_random_uuid()`, que viene de serie desde PostgreSQL 13. Mínimo exigido por el esquema: 13; usado: 16.

**Frontend del chat** (`src/app/static/chat/`): HTML y JavaScript propios, sin bibliotecas externas ni CDN.

## 4. Modelos de lenguaje

| Modelo | Para qué | Dónde |
|---|---|---|
| `qwen3:14b` (Ollama) | evaluador 0/1/2 y variación de frase; el prompt se afinó con él; PC de Álvaro (RTX 5060 Ti 16 GB) | `environment/.env.example` (`OLLAMA_MODEL`, `LLM_COMPAT_MODEL`) |
| `gpt-oss:20b` | autor de la batería 3 (otra familia que el evaluador) | `src/tests/data/bateria_valoracion_3.json` |
| `qwen3:0.6b` | solo la prueba del protocolo `openai` del 25/10/2026 (CPU) | `README.md` y `docs/api-conversacion.md` (llegan con la PR n.º 4) |
| `simulado` (LLM falso por reglas) | modo sin GPU; versión del evaluador `simulado-2026-10-25+<hash>` | `src/app/simulado.py`, `docs/modo-simulado.md` (PR n.º 4) |
| Ollama 0.40.11 | servidor con el que se midió el protocolo `openai` el 25/10/2026 (sandbox, sin GPU) | `README.md` y `docs/api-conversacion.md` (PR n.º 4) |

### El PC de las mediciones (Windows 11, RTX 5060 Ti)

Leído el 25/10/2026 de los ficheros del propio PC, en solo lectura. **Los registros del 12/10 ya no existen** (los más antiguos de Ollama son del 17/10), así que lo que cambia con el tiempo se da con la fecha de la fuente más cercana.

| Elemento | Valor | Fuente (fecha) | ¿Vale para el 12/10? |
|---|---|---|---|
| Equipo | Ryzen 7 5800X · 32 GB · RTX 5060 Ti 16 GB (15,9 GiB visibles, Blackwell, compute 12.0) · Windows 11 Pro, build 22631 | `C:\IA LOCAL\MANIFIESTO.md` (03/09); registro de Ollama (25/10) | Sí |
| `qwen3:14b` | manifiesto `sha256:8d6c98e1c8dbb1d0efa1522a150672d846a79c8f9b6b6e4309ab6a17c90dd038` (ID de `ollama list`: `8d6c98e1c8db`); GGUF `sha256:a8cc1361f3145dc01f6d77c6c82c9116b9ffe3c97b34716fe20418455876c40e`, 9.276.184.896 bytes, 14,8 B parámetros; **cuantización Q4_K_M** (`general.file_type = 15` en la cabecera del GGUF y `Q4_K_M` en el manifiesto) | `C:\Users\agarc\.ollama\models` (25/10): manifiesto escrito el 05/09/2026 01:45; el mismo ID consta en `C:\IA LOCAL\_publicar\d1-decision-bench\docs\METHOD.md` (09/10) | **Sí**: descargado antes del 12/10 y con el mismo ID el 09/10 |
| Ollama | 0.34.4 (09/10) → 0.40.3 (17/10) → 0.40.6 (desde el 18/10 a las 17:26; es la actual) · la 0.40.11 está descargada y sin instalar | `METHOD.md` (09/10); `server-5.log` (17/10); `upgrade.log` y `app.log` (18/10 y 25/10) | **No se sabe cuál**: el 12/10 estaba entre la 0.34.4 y la 0.40.3 |
| Opciones del servidor Ollama | contexto 131072, flash attention activada, caché KV `q4_0`, `keep alive` 5 min, un modelo cargado, una petición a la vez, escucha en 0.0.0.0:11434 | `server-5.log` (17/10) y `server.log` (25/10), iguales; ya estaban recomendadas en `C:\IA LOCAL\README.md` | Probable |
| Controlador NVIDIA | 617.14 (09/10); 616.56 (03/09); CUDA del controlador 13.4 (17/10 y 25/10) | `METHOD.md`; `MANIFIESTO.md`; registros de Ollama | **Probable 617.14**. No se pudo leer el registro del propio controlador (se denegó el acceso al almacén de controladores) |
| Docker Desktop | 4.75.0 (227598), instalada el 02/06/2026; motor 29.5.2; Compose v5.1.3 y WSL2 2.7.12 (03/09, sin revalidar) | `AppData\Local\Docker\install-log.txt`; `electron-*.log` del 14/10 al 25/10; `MANIFIESTO.md` | **Sí**: misma versión desde el 02/06, sin actualizaciones registradas |

Lo que ya no se puede recuperar es la versión exacta de Ollama y el controlador del 12/10. Para que no vuelva a pasar, **cada medición con LLM real anota estas cuatro líneas** (apartado 9).

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

Umbrales: F1-macro ≥ 0,75; recall y precisión de estancamiento ≥ 0,65. Las cifras del informe de validación, de ADR-001 y de `src/generador/ORIGEN.md` son mediciones fechadas con la pila anterior y se dejan como estaban. **La memoria debe citar las de scikit-learn 1.9.1.** Tras cambiar de versión hay que reentrenar (`make train`): el modelo guardado (`src/models/`, no versionado) es un fichero joblib que scikit-learn avisa de que no debe cargarse con otra versión.

## 7. Divergencias y su estado

| Id | Divergencia | Estado |
|---|---|---|
| D-01 | nf3 (`main`, PR n.º 1–4) y las tres ramas de Soultech usan numpy 2.2.1, pandas 2.2.3, scikit-learn 1.6.1, pyyaml 6.0.2 y Python 3.11; el NF2 documenta las versiones del apartado 2 | nf3: se resuelve al fusionar la PR n.º 5. Soultech: sin tocar (decidir al unificar con nf3) |
| D-02 | streamlit 1.41.1 → 1.56.0: no figura en el NF2; es consecuencia de pandas 3 | Visto bueno de Álvaro el 25/10/2026; falta la conformidad de Marcos (revisión de la PR n.º 5) |
| D-03 | README del repo académico: «Python 3.11 o superior; probado con 3.13», pero numpy 2.5.3 exige 3.12 | Abierta (repo de Marcos) |
| D-04 | README del repo académico cita `environment/requirements.txt`; el fichero está en la raíz (`environment/` solo tiene `.gitkeep`) | Abierta (repo de Marcos) |
| D-05 | El NF2 promete «Docker Compose con versiones fijadas», pero `ollama/ollama:latest` no está fijada y `postgres:16-alpine` y `python:3.12-slim` fijan solo la versión mayor | Abierta: decidir si se fija la etiqueta exacta (o el digest) |
| D-06 | Solo se fijan las dependencias directas; las transitivas (starlette, scipy, pyarrow…) las resuelve pip al construir (apartado 8) | Abierta: valorar un fichero de restricciones (`pip freeze`) |
| D-07 | Cifras del clasificador del 12/10/2026 medidas con scikit-learn 1.6.1 (apartado 6) | Documentada; la memoria cita las nuevas |
| D-08 | Versiones de Ollama, `qwen3:14b`, Docker Desktop y controlador NVIDIA del PC de Álvaro sin anotar | Cerrada el 25/10/2026 (apartado 4) salvo dos datos irrecuperables: la versión exacta de Ollama y el controlador del 12/10 |
| D-09 | `.env.example` nombra `TABBYAPI_MODEL=Qwen3.8-27B-EXL3-3.0bpw` (perfil opcional de TabbyAPI) | Declarado en el repositorio, no comprobado |

## 8. Resolución de las dependencias transitivas (25/10/2026, informativa)

Resultado de `pip install -r src/requirements-dev.txt -r src/dashboard/requirements.txt` en Python 3.12.3. No es una restricción: sirve para ver si una imagen futura se ha movido.

altair 6.3.0 · annotated-types 0.8.0 · anyio 4.15.1 · attrs 26.1.0 · blinker 1.9.0 · cachetools 7.2.5 · certifi 2026.10.23 · charset-normalizer 3.5.2 · click 8.5.0 · gitdb 4.0.12 · GitPython 3.2.1 · greenlet 3.5.6 · h11 0.16.0 · httpcore 1.0.9 · httptools 0.9.0 · idna 3.20 · iniconfig 2.3.1 · Jinja2 3.1.6 · jsonschema 4.26.0 · jsonschema-specifications 2025.9.1 · MarkupSafe 3.0.4 · narwhals 2.27.1 · packaging 26.3 · pillow 12.3.0 · pluggy 1.7.0 · protobuf 7.36.2 · pyarrow 26.0.0 · pydantic-core 2.27.2 · pydeck 0.9.3 · python-dateutil 3.0.0 · referencing 0.37.0 · requests 2.34.2 · rpds-py 2026.9.1 · scipy 1.18.1 · six 1.17.0 · smmap 5.0.3 · starlette 0.41.3 · tenacity 9.2.1 · threadpoolctl 3.7.0 · toml 0.10.2 · tornado 6.6 · typing-extensions 4.16.0 · urllib3 2.8.0 · uvloop 0.23.0 · watchdog 6.0.0 · watchfiles 1.3.0 · websockets 17.3

## 9. Cómo volver a comprobarlo

```bash
cd src && python -m pytest tests/test_versiones.py          # esta lista frente a requirements*.txt, Dockerfile y compose
python -m pip install -r requirements-dev.txt -r dashboard/requirements.txt && python -m pip check
docker compose -f ../environment/docker-compose.yml --env-file ../environment/.env exec backend \
  python -c "import sys,numpy,pandas,sklearn,yaml;print(sys.version.split()[0],numpy.__version__,pandas.__version__,sklearn.__version__,yaml.__version__)"
docker compose -f ../environment/docker-compose.yml --env-file ../environment/.env exec db postgres --version
```

En el PC, antes de cada medición con el LLM real (PowerShell), y se copian los resultados al informe de esa medición:

```powershell
ollama --version                                                    # versión de Ollama
ollama list | Select-String "qwen3:14b"                             # ID del modelo (8d6c98e1c8db)
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader    # controlador NVIDIA
docker version --format "Docker Desktop: {{.Server.Platform.Name}} · motor {{.Server.Version}}"
```
