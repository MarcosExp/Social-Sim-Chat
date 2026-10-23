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
git merge nf3/main --allow-unrelated-histories      # conflictos esperados: .gitignore, README.md, src/ml/features.py, src/ml/evaluar_corpus.py
git push -u origin entrega-nf3                       # y PR entrega-nf3 -> main en GitHub
```

- Resolver los conflictos a mano. **No usar `-X theirs`**: `src/ml/` del repo académico es más reciente que la copia de nf3 (ver `src/generador/ORIGEN.md`) y se pisaría.
- Se conserva el historial de los dos repos (el de Marcos y el de nf3).
- Del repo académico siguen existiendo `config.yaml`, `requirements.txt`, los diagramas de NF2 (`docs/er.*`, `docs/arquitectura.*`) y los documentos de NF2; hay que decidir qué se queda y qué se mueve a una carpeta de historial para que el ER vigente (`docs/er_v2.*`) sea el único a la vista.
- Escribir en el repo académico requiere permiso de Marcos.

Autoría y licencia: ver [`AUTORIA.md`](AUTORIA.md).
