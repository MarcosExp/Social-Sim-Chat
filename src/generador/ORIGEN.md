# Origen de estos ficheros

Copiados SIN modificar el 12/10/2026 desde `MarcosExp/Social-Sim-Chat`, PR #2
(commit `5d85eb0`, "Generador de corpus corregido, features de ventana y
evaluación antifuga"), autor: Marcos Expósito Flox. Actualizados el 23/10/2026 (ver abajo).

- `src/generador/generador_corpus_sintetico.py` y `src/generador/config.yaml`
- `src/ml/features.py` y `src/ml/evaluar_corpus.py`
- `docs/validacion/informe_metricas_marcos.json` (informe de referencia de Marcos)

**Actualización del 23/10/2026:** los ficheros de `src/ml/`, `src/generador/config.yaml` y el informe de referencia se han
puesto al día, también sin modificar, con el último commit de Marcos que los toca: `4e2be4e` («Features leen config.yaml y
agrupan por alumno y competencia; informe por semilla en reports/»; `main` del repo de Marcos = `95f349c`). La nueva
`features.py` ya no exporta `VENTANA` ni `COLUMNAS_FEATURES`: los lee de la config, y el adaptador `src/app/ml_config.py`
(nuestro) los resuelve para el backend y los scripts. Comprobado: features idénticas a las de la versión anterior
(diferencia máxima 0,0) y mismo entrenamiento (F1-macro 0,793; recall de estancamiento 0,670; precisión 0,741).

**Cambio del 26/10/2026 (hecho en nf3 por Marcos, autor del fichero):** `generador_corpus_sintetico.py` añade la columna
`nivel_ruido` a `corpus_meta.csv` (`alto` en Deixis, `medio` en el resto; punto 5 de la llamada). Es un valor derivado de la
competencia, sin tiradas aleatorias: `corpus_train.csv` sale idéntico byte a byte con las semillas 42, 7 y 123, y
`corpus_meta.csv` solo gana la columna. Este cambio todavía no está en el repo de Marcos: se lleva allí con la entrega
(rama `entrega-nf3`), y hasta entonces este fichero es la versión de referencia.

Salvo el cambio de `nivel_ruido` de arriba, cualquier cambio se hace fuera de estos ficheros (adaptadores como
`src/app/ml_config.py`) para poder reabsorber futuras versiones de Marcos sin conflictos.
Ver `AUTORIA.md` en la raíz del repositorio.
