# Cómo se trabaja en este repositorio

`nf3/main` es el **tronco común** del prototipo SOCIAL-SIM Chat. Los demás repositorios derivan de él en un solo sentido.

| Repositorio | Papel | Regla |
|---|---|---|
| `cCoolBoox/social-sim-chat-nf3` (privado) | Tronco | Todo el código compartido se escribe aquí. |
| `MarcosExp/Social-Sim-Chat` (público) | Espejo de entrega | Solo recibe la rama `entrega-nf3` (fusión de `nf3/main`, ver «Entrega»), la memoria en PDF y el tag `fase2_grupo12`. |
| Copia de Soultech Labs (privada) | Tronco + material interno | Se actualiza con `git merge nf3/main`; nada compartido se edita primero allí. |

## Flujo
1. Rama desde `main` (`feature/<tema>`), cambios pequeños, PR a `main`.
2. Antes del PR: `make test` en verde. Si tocas el esquema, añade una migración nueva (no reescribas las anteriores) e idempotente: `src/tests/test_migraciones.py` las reaplica todas.
3. Los datos de tu máquina (conteos, claves, rutas) no entran en scripts compartidos: van como parámetro.
4. Se respetan los finales de línea existentes (`.ps1` y `001_schema.sql` son CRLF).
5. Si tu cambio altera lo que dice el README o `docs/`, se actualiza en el mismo PR.

## Calendario de entrega
| Fecha | Hito |
|---|---|
| 27/10 | Se congela el tronco: todo lo que depende de Marcos fusionado y `docker compose up` funcionando en `main`. |
| 28/10 - 09/11 | Solo arreglos de Álvaro. |
| 12/11 | Entrega: PR `entrega-nf3` → `main` en `MarcosExp/Social-Sim-Chat`, `fase2_grupo12.pdf` y tag `fase2_grupo12`. |

## Entrega al repo académico
`nf3` y `MarcosExp/Social-Sim-Chat` **no comparten historial** (nf3 nació como repo nuevo), así que GitHub no permite un PR de `nf3/main` hacia el otro repo. Se hace dentro del repo académico, con una rama que fusiona los dos historiales:

```bash
git clone https://github.com/MarcosExp/Social-Sim-Chat && cd Social-Sim-Chat
git remote add nf3 https://github.com/cCoolBoox/social-sim-chat-nf3.git && git fetch nf3
git checkout -b entrega-nf3 origin/main
git merge nf3/main --allow-unrelated-histories      # conflictos: .gitignore, README.md y src/generador/generador_corpus_sintetico.py
git push -u origin entrega-nf3                       # y PR entrega-nf3 -> main en GitHub
```

- Resolver los conflictos a mano; en los tres prevalece el de nf3 (el 11/11/2026 se comprobó que su `.gitignore` contiene todas las líneas del otro y añade `src/models/`, y que el generador solo difiere en la columna `nivel_ruido`, de la PR n.º 7 de Marcos). Después, el README se adapta: el `git clone` de «Arrancarlo sin GPU» apunta a este repositorio, porque el de trabajo es privado. **No usar `-X theirs`**: si Marcos cambia algo en su repo después, se pisaría sin avisar. `src/ml/` no da conflicto porque nf3 tiene la misma versión que su `main` (`4e2be4e`).
- Se conserva el historial de los dos repos (el de Marcos y el de nf3).
- Del repo académico siguen existiendo `config.yaml`, `requirements.txt` (sus cuatro versiones —numpy 2.5.3, pandas 3.0.5, scikit-learn 1.9.1 y PyYAML 6.0.3— coinciden con `src/requirements.txt` desde el 25/10/2026, y las imágenes usan `python:3.12.15-slim` (con digest) porque numpy 2.5.3 pide Python 3.12; queda decidir si se retira o se deja como referencia del NF2; la lista completa de versiones y sus divergencias está en [`docs/versiones.md`](docs/versiones.md)), los diagramas de NF2 (`docs/er.*`, `docs/arquitectura.*`) y los documentos de NF2; hay que decidir qué se queda y qué se mueve a una carpeta de historial para que el ER vigente (`docs/er_v2.*`) sea el único a la vista.
- Escribir en el repo académico requiere permiso de Marcos.

Autoría y licencia: ver [`AUTORIA.md`](AUTORIA.md).
