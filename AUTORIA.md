# Autoría y procedencia

Prototipo del Grupo 12 (Módulo C088, iFP). Este fichero declara quién escribió qué para que la entrega sea honesta
con la autoría y para decidir con conocimiento cualquier publicación posterior.

## Código de Marcos Expósito Flox (copiado sin modificar)

Origen: `MarcosExp/Social-Sim-Chat`, PR #2, copiado el 12/10/2026 (commit `5d85eb0`) y actualizado el 23/10/2026 a `4e2be4e`. Detalle en `src/generador/ORIGEN.md`.

- `src/generador/generador_corpus_sintetico.py`, `src/generador/config.yaml`
- `src/ml/features.py`, `src/ml/evaluar_corpus.py`
- `docs/validacion/informe_metricas_marcos.json`

## Código y documentación de Álvaro García Puche

- Backend `src/app/` (API, conversación con Ollama, métricas reales, autenticación, correcciones), migraciones 002→013,
  dashboard `src/dashboard/`, chat `src/app/static/chat/`, scripts de `src/scripts/` salvo los heredados, tests `src/tests/`,
  `environment/`, `scripts/`, `Makefile` y la documentación de `docs/` (salvo los JSON de validación).
- Desarrollado con ayuda de Claude (Anthropic) como asistente de programación; los commits llevan esa atribución.
- **Historial de Git.** Los commits cuyo autor Git es «Claude» (`Claude <noreply@anthropic.com>`) los hizo y subió Claude Code a partir de
  propuestas de Álvaro, que decidió qué se hacía y ordenó cada fusión; llevan la línea `Co-Authored-By`. Las fusiones de las
  pull requests salen de la cuenta de Álvaro (`cCoolBoox`) y los commits de Marcos llevan su nombre. Por eso `git shortlog` no
  dice por sí solo quién decidió cada cambio: para eso sirve este fichero y el apartado de reparto de trabajo de la memoria.

## Material de equipo (a confirmar entre los dos)

- `src/scripts/generador_corpus_sintetico.py` (generador anterior, heredado del NF1) y `src/app/guiones/guiones.json`
  (transcripción de `Guiones_Dialogo.md`, NF1): trabajo del equipo en el entregable NF1.
- `data/init-db/001_schema.sql`: esquema inicial del NF2.

## Uso de inteligencia artificial
Declarado según las instrucciones de entrega del módulo (el uso de IA está permitido y debe indicarse dónde y cómo):
- **Claude (Anthropic), como asistente de programación** con Claude Code: escritura y revisión de código del backend, dashboard, migraciones, scripts y tests (Álvaro), depuración, refactorizaciones y generación de la documentación técnica (ADR, contratos de API, informes de validación, este repositorio). **La memoria (`fase2_grupo12.pdf`) también se ha redactado con ayuda de Claude** a partir del repositorio y de los informes de medición. El autor ejecutó y verificó el resultado (tests y pruebas manuales en su entorno); el recuento de pruebas lo da `pytest` (`make test`) y no se copia en el README.
- **LLM local (Ollama, modelo `qwen3:14b`) como parte del producto**, no como herramienta de desarrollo: genera la variación de frase y la valoración 0/1/2 del turno del menor durante la conversación.
- **Modo simulado y baterías de validación** (herramientas de desarrollo y prueba, no IA dentro del producto): las reglas de `src/app/simulado.py` (un LLM falso sin modelo) y la batería 4 (`src/tests/data/bateria_valoracion_4.json`, 104 respuestas) las escribió Claude Sonnet 5.5 con Claude Code, la batería sin consultar las reglas y antes de medirlas. La batería 3 la generó `gpt-oss:20b` (Ollama, en local). Las etiquetas de ambas **no las ha revisado ninguna persona** (hojas en `docs/revision-bateria-3.md` y `docs/revision-bateria-4.md`). Método y límites: `docs/adr/ADR-004_puntuacion_012_solo_llm.md`.
- **Código de Marcos** (`src/generador/`, `src/ml/`): su uso de IA, si lo hubo, lo declara él en su parte de la memoria.

## Terceros
Software que se usa pero **no se redistribuye** en este repositorio (cada uno con su licencia): Python, FastAPI, SQLAlchemy, Pydantic, PostgreSQL 16, Streamlit, Plotly, pandas, NumPy, scikit-learn, joblib, httpx, PyYAML, pytest, Docker, Ollama y el modelo Qwen3 (Alibaba Cloud). Versiones fijadas en `src/requirements*.txt`.

## Licencia

El código y la documentación propios de este repositorio se publican bajo la **PolyForm Noncommercial License 1.0.0**
(<https://polyformproject.org/licenses/noncommercial/1.0.0>); el texto completo y el aviso de autoría están en
[`LICENSE`](LICENSE). En resumen: se puede usar, estudiar y modificar para fines no comerciales (investigación,
docencia, uso personal o de organizaciones sin ánimo de lucro); **el uso comercial no está permitido** sin permiso
de los autores. Es una licencia de «código disponible», no una licencia de código abierto en el sentido de la OSI.

Alcance: cubre lo escrito por Álvaro y por Marcos en este repositorio. No cubre el software de terceros de la sección
anterior (cada uno conserva su licencia, y no se redistribuye aquí), ni los modelos de lenguaje que el usuario descargue.
Los datos del corpus son sintéticos y se publican con el mismo régimen. No es asesoramiento legal.
