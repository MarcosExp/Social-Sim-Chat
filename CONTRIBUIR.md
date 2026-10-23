# Cómo se trabaja en este repositorio

`nf3/main` es el **tronco común** del prototipo SOCIAL-SIM Chat. Los demás repositorios derivan de él en un solo sentido.

| Repositorio | Papel | Regla |
|---|---|---|
| `cCoolBoox/social-sim-chat-nf3` (privado) | Tronco | Todo el código compartido se escribe aquí. |
| `MarcosExp/Social-Sim-Chat` (público) | Espejo de entrega | Solo recibe PR desde `main` de este repo, la memoria en PDF y el tag `fase2_grupo12`. |
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
| 12/11 | Entrega: PR a `MarcosExp/Social-Sim-Chat`, `fase2_grupo12.pdf` y tag `fase2_grupo12`. |

Autoría y licencia: ver [`AUTORIA.md`](AUTORIA.md).
