# Origen de estos ficheros

Copiados SIN modificar el 12/10/2026 desde `MarcosExp/Social-Sim-Chat`, PR #2
(commit `5d85eb0`, "Generador de corpus corregido, features de ventana y
evaluación antifuga"), autor: Marcos Expósito Flox.

- `src/generador/generador_corpus_sintetico.py` y `src/generador/config.yaml`
- `src/ml/features.py` y `src/ml/evaluar_corpus.py`
- `docs/validacion/informe_metricas_marcos.json` (informe de referencia de Marcos)

**Desfase conocido (comprobado el 23/10/2026):** el `main` del repo de Marcos tiene una versión posterior de
`src/ml/features.py` y `src/ml/evaluar_corpus.py` (commit `4e2be4e`, «Features leen config.yaml y agrupan por alumno y
competencia; informe por semilla en reports/», también en el PR #2) y su `config.yaml` añade el bloque `features`
(`ventana`, `n_base`). La copia de este repo es la del commit `5d85eb0`, anterior. La versión nueva ya no exporta
`VENTANA` ni `COLUMNAS_FEATURES`, que usan `src/app/routers/students.py`, `src/scripts/train_classifier.py` y
`src/scripts/semillas_clasificador.py`: sincronizarla tal cual rompe esos tres ficheros. Pendiente de acordar con Marcos
cuál es la versión de referencia.

Cualquier cambio se hace fuera de estos ficheros (adaptadores en `src/scripts/`)
para poder reabsorber futuras versiones de Marcos sin conflictos.
Ver `AUTORIA.md` en la raíz del repositorio.
