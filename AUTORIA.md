# Autoría y procedencia

Prototipo del Grupo 12 (Módulo C088, iFP). Este fichero declara quién escribió qué para que la entrega sea honesta
con la autoría y para decidir con conocimiento cualquier publicación posterior.

## Código de Marcos Expósito Flox (copiado sin modificar)

Origen: `MarcosExp/Social-Sim-Chat`, PR #2, commit `5d85eb0` (12/10/2026). Detalle en `src/generador/ORIGEN.md`.

- `src/generador/generador_corpus_sintetico.py`, `src/generador/config.yaml`
- `src/ml/features.py`, `src/ml/evaluar_corpus.py`
- `docs/validacion/informe_metricas_marcos.json`

## Código y documentación de Álvaro García Puche

- Backend `src/app/` (API, conversación con Ollama, métricas reales, autenticación, correcciones), migraciones 002→011,
  dashboard `src/dashboard/`, chat `src/app/static/chat/`, scripts de `src/scripts/` salvo los heredados, tests `src/tests/`,
  `environment/`, `scripts/`, `Makefile` y la documentación de `docs/` (salvo los JSON de validación).
- Desarrollado con ayuda de Claude (Anthropic) como asistente de programación; los commits llevan esa atribución.

## Material de equipo (a confirmar entre los dos)

- `src/scripts/generador_corpus_sintetico.py` (generador anterior, heredado del NF1) y `src/app/guiones/guiones.json`
  (transcripción de `Guiones_Dialogo.md`, NF1): trabajo del equipo en el entregable NF1.
- `data/init-db/001_schema.sql`: esquema inicial del NF2.

## Uso de inteligencia artificial
Declarado según las instrucciones de entrega del módulo (el uso de IA está permitido y debe indicarse dónde y cómo):
- **Claude (Anthropic), como asistente de programación** con Claude Code: escritura y revisión de código del backend, dashboard, migraciones, scripts y tests (Álvaro), depuración, refactorizaciones y generación de la documentación técnica (ADR, contratos de API, informes de validación, este repositorio). El autor ejecutó y verificó el resultado (tests y pruebas manuales en su entorno); la suite tiene 159 pruebas.
- **LLM local (Ollama, modelo `qwen3:14b`) como parte del producto**, no como herramienta de desarrollo: genera la variación de frase y la valoración 0/1/2 del turno del menor durante la conversación.
- **Código de Marcos** (`src/generador/`, `src/ml/`): su uso de IA, si lo hubo, lo declara él en su parte de la memoria.

## Terceros
Software que se usa pero **no se redistribuye** en este repositorio (cada uno con su licencia): Python, FastAPI, SQLAlchemy, Pydantic, PostgreSQL 16, Streamlit, Plotly, pandas, NumPy, scikit-learn, joblib, httpx, PyYAML, pytest, Docker, Ollama y el modelo Qwen3 (Alibaba Cloud). Versiones fijadas en `src/requirements*.txt`.

## Licencia

**No hay licencia todavía.** Sin licencia, todos los derechos quedan reservados por sus autores y nadie más puede
reutilizar el código. La decisión (permisiva tipo MIT/Apache-2.0, o de uso no comercial) debe tomarse entre Marcos y
Álvaro antes de hacer público nada, y depende de si la entrega exige un repositorio público. No es asesoramiento legal.
