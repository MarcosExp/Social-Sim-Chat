# API del dashboard (ADR-003)

El dashboard solo habla con esta API (REST JSON; documentación interactiva en `/docs`). Cualquier regla de negocio vive en el backend.

## Acceso
- **Clave del terapeuta:** cabecera `X-API-Key` = `API_KEY_TERAPEUTA`. En `docker compose` es obligatoria (por defecto `dev-terapeuta-local`, solo desarrollo); fuera de compose, vacía = API abierta. `GET /health` informa de `auth_terapeuta` (`activa`/`desactivada`).
- **Quién corrige:** los `PATCH` exigen `X-Terapeuta: <nombre>`, codificado en porcentaje porque las cabeceras HTTP son ASCII (`Álvaro` → `%C3%81lvaro`; un nombre sin acentos vale tal cual). Se guarda en `correccion_log`; **no está verificado**.
- **Abiertos (sin clave):** `GET /health`, `GET /`, `/chat`, `GET /conversaciones/alumnos` y el flujo del menor (`POST /conversaciones`, `POST /conversaciones/{id}/turnos`).
- Es autenticación de **prototipo** (clave compartida, sin usuarios ni roles). No basta para datos reales de menores.

## Lectura (requiere clave)
| Endpoint | Contenido |
|---|---|
| `GET /resumen` | conteos y distribuciones de la cabecera |
| `GET /students`, `GET /students/{id}` | alumnos simulados |
| `GET /students/{id}/prediccion` | puerta de predicción sobre sesiones **reales**: `disponible`, `ventana_requerida`, conteos y `motivos` |
| `GET /sessions` (`origen`, `student_id`), `GET /sessions/by-student/{id}` | sesiones (sin `nota_clinica`) |
| `GET /sessions/{id}` | detalle, con `nota_clinica` (dato sensible) |
| `GET /predicciones` (`student_id`, `modelo_version`, `todas_las_versiones`) | por defecto, la última versión del modelo |
| `GET /modelo/metricas` | métricas y anti-fuga (404 `modelo_no_entrenado` si no hay modelo) |
| `GET /conversaciones` (`student_id`, `incluir_pruebas`), `GET /conversaciones/{id}` | conversaciones reales y sus turnos |
| `GET /conversaciones/{id}/figuras` | una fila por figura (vista `turn_data`, ADR-002) |
| `GET /correcciones` (`session_id`, `conversacion_id`, `limite`) | historial de correcciones |

## Escritura (requiere clave y `X-Terapeuta`)
| Endpoint | Efecto |
|---|---|
| `PATCH /conversaciones/{id}/turnos/{orden}` `{accuracy_corregido: 0\|1\|2\|null}` | corrige la valoración de un turno del menor; recalcula `iniciativa` y las métricas de la sesión; 409 si la conversación no está terminada o el turno no es valorable |
| `PATCH /sessions/{id}/correccion` `{etiqueta_corregida?, nota_clinica?}` | etiqueta (`progreso`/`estancamiento`/`regresion`) y nota clínica (máx. 2000) |

Cada cambio real queda en `correccion_log`; repetir el mismo valor no genera fila; de la nota clínica solo consta que cambió.

## Fechas
La API y la BD devuelven las fechas en **UTC** (`...Z`). El dashboard las muestra en **hora peninsular** (Europe/Madrid; Canarias va 1 h por detrás) y lo indica en el título de cada columna y en el pie de la tabla.
