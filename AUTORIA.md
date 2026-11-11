# Autoría y procedencia

Prototipo del Grupo 12 (Módulo C088, iFP). Este fichero declara quién escribió qué para que la entrega sea honesta
con la autoría y para decidir con conocimiento cualquier publicación posterior.

## Código de Marcos Expósito Flox (copiado, con una sola modificación)

Origen: `MarcosExp/Social-Sim-Chat`, PR #2, copiado el 12/10/2026 (commit `5d85eb0`) y actualizado el 23/10/2026 a `4e2be4e`. Detalle en `src/generador/ORIGEN.md`.

- `src/generador/generador_corpus_sintetico.py`, `src/generador/config.yaml`
- `src/ml/features.py`, `src/ml/evaluar_corpus.py`
- `docs/validacion/informe_metricas_marcos.json`

La única modificación hecha en este repositorio es de Marcos: `generador_corpus_sintetico.py` añade la columna `nivel_ruido` (26/10/2026, PR n.º 7; `src/generador/ORIGEN.md`). Marcos escribió además directamente aquí `src/scripts/generar_turnos.py`, `src/tests/test_generar_turnos.py` y su llamada desde `seed_corpus.py` (PR n.º 9).

## Código y documentación de Álvaro García Puche

- Backend `src/app/` (API, conversación con Ollama, métricas reales, autenticación, correcciones), migraciones 002→013,
  dashboard `src/dashboard/`, chat `src/app/static/chat/`, scripts de `src/scripts/` salvo los heredados, tests `src/tests/`,
  `environment/`, `scripts/`, `Makefile` y la documentación de `docs/` (salvo los JSON de validación).
- Reparto con la IA, según Álvaro: el marco conceptual (su TFM de 2020, más abajo), la especificación, las decisiones y la revisión de cada
  cambio son suyos; el desarrollo (código, tests y documentación técnica) lo aportó Claude (Anthropic) con Claude Code a partir de sus
  indicaciones. Los commits llevan esa atribución.
- **Historial de Git.** Los commits cuyo autor Git es «Claude» (`Claude <noreply@anthropic.com>`) los hizo y subió Claude Code a partir de
  propuestas de Álvaro, que decidió qué se hacía y ordenó cada fusión; llevan la línea `Co-Authored-By`. Las fusiones de las
  pull requests salen de la cuenta de Álvaro (`cCoolBoox`) y los commits de Marcos llevan su nombre. Por eso `git shortlog` no
  dice por sí solo quién decidió cada cambio: para eso sirve este fichero y el apartado de reparto de trabajo de la memoria. Desde el 27/10/2026 los commits que hace Claude Code se firman con el nombre de Álvaro y conservan la línea `Co-Authored-By: Claude`, de modo que el uso de IA sigue constando en cada uno; el historial anterior no se ha reescrito.

## Procedencia de la plataforma y reparto respecto al NF2

La primera revisión de este repositorio (`219a960`, 23/10/2026) es una instantánea depurada de un repositorio privado de
Soultech Labs, la empresa de Álvaro: backend, migraciones 001 a 011, dashboard, chat, clasificador, tests y documentación de
las API, sin documentos internos ni material del curso. La historia anterior de esas piezas está en aquel repositorio y no en
este. El NF2 ya lo declaró en su anexo B como origen del código del chat y del dashboard.

El NF2 (secciones 1 y 11) asignó a Marcos la plataforma (backend, base de datos, Docker Compose, API, conversación, puntuación
0/1/2, métricas, entrenamiento y predicción) además del generador y el clasificador, y a Álvaro el dominio pedagógico, las
métricas, el dashboard y el chat. En NF3 la plataforma la aporta Álvaro, desde ese repositorio y con ayuda de Claude, y Marcos
aporta el generador de corpus, las features, el clasificador, `generar_turnos.py` y `nivel_ruido`. El detalle por bloque está en
el apartado de reparto de trabajo de la memoria.

Motivo del cambio, según Álvaro y confirmado por Marcos el 27/10/2026: Álvaro había avanzado en paralelo en el desarrollo de
la aplicación sobre su pila local (Docker con Ollama y `qwen3:14b`), donde hizo todas las pruebas, de modo que cuando se repartió
el trabajo del NF3 ya tenía datos y frontend, y la plataforma pasó a su lado. El cambio se acordó durante el NF3; Marcos no recuerda la fecha exacta. Ese LLM local es parte del producto y se declara en
el apartado «Uso de inteligencia artificial»; el desarrollo del código lo aportó Claude, como se indica arriba.

## Material de equipo (a confirmar entre los dos)

- `src/scripts/generador_corpus_sintetico.py` (generador anterior, heredado del NF1) y `src/app/guiones/guiones.json`
  (transcripción de `Guiones_Dialogo.md`, NF1): trabajo del equipo en el entregable NF1.
- `data/init-db/001_schema.sql`: esquema inicial del NF2.

## Trabajo previo de uno de los autores

El proyecto parte del TFM de 2020 de Álvaro García Puche, «Síndrome de Asperger-chatbot: comunicación y sus efectos en las
relaciones sociales» (Máster Universitario en Tecnología Educativa y Competencias Digitales, Universidad Internacional de La Rioja;
Proyecto de Innovación dirigido por Dyanne Ruiz Castañeda; 23/09/2020). Es obra individual de Álvaro; Marcos no participó en él.
De ese trabajo salen la idea de partida, los tres tramos de edad (6-8, 8-10 y 10-12 años), las cuatro competencias pragmáticas y la
estructura de ramas del guion de apertura de `src/app/guiones/guiones.json`, adaptada de su Anexo A. El documento del TFM no está
en este repositorio. En `docs/`, «TFM» a secas designa la documentación del proyecto del módulo (NF1 y NF2), no ese trabajo.

## Uso de inteligencia artificial
Declarado según las instrucciones de entrega del módulo (el uso de IA está permitido y debe indicarse dónde y cómo):
- **Claude (Anthropic), con Claude Code, aportó el desarrollo**: escritura y revisión de código del backend, dashboard, migraciones, scripts y tests (Álvaro), depuración, refactorizaciones y generación de la documentación técnica (ADR, contratos de API, informes de validación, este repositorio). **La memoria (`fase2_grupo12.pdf`) también se ha redactado con ayuda de Claude** a partir del repositorio y de los informes de medición. El autor ejecutó y verificó el resultado (tests y pruebas manuales en su entorno); el recuento de pruebas lo da `pytest` (`make test`) y no se copia en el README.
- **LLM local (Ollama, modelo `qwen3:14b`) como parte del producto**, no como herramienta de desarrollo: genera la variación de frase y la valoración 0/1/2 del turno del menor durante la conversación.
- **Modo simulado y baterías de validación** (herramientas de desarrollo y prueba, no IA dentro del producto): las reglas de `src/app/simulado.py` (un LLM falso sin modelo) y la batería 4 (`src/tests/data/bateria_valoracion_4.json`, 104 respuestas) las escribió Claude Sonnet 5.5 con Claude Code, la batería sin consultar las reglas y antes de medirlas. La batería 3 la generó `gpt-oss:20b` (Ollama, en local). Las etiquetas de ambas las revisó Marcos el 27/10/2026, con ayuda de Claude, que propuso los cambios (la decisión en cada caso es suya): cambió 16 (15 en la batería 3 y 1 en la 4). No es la anotación de un terapeuta ni una revisión sin IA (hojas en `docs/revision-bateria-3.md` y `docs/revision-bateria-4.md`). Método y límites: `docs/adr/ADR-004_puntuacion_012_solo_llm.md`.
- **Código de Marcos** (`src/generador/`, `src/ml/` y `src/scripts/generar_turnos.py`): Marcos declara (27/10/2026) que ha usado únicamente Claude Code como agente de código, para crear el generador de corpus y el código de aprendizaje automático (`src/generador/` y `src/ml/`) y, en NF3, para `nivel_ruido`, `generar_turnos.py` y la revisión de las baterías 3 y 4. Sobre cómo lo revisa, declara que todo lo que hace Claude lo lee, lo verifica y lo prueba antes de hacer push o de incorporarlo (27/10/2026; es su declaración y este repositorio no la puede comprobar).

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
