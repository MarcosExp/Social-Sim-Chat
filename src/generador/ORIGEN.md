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

Cualquier cambio se hace fuera de estos ficheros (adaptadores en `src/scripts/`)
para poder reabsorber futuras versiones de Marcos sin conflictos.
Ver `AUTORIA.md` en la raíz del repositorio.
