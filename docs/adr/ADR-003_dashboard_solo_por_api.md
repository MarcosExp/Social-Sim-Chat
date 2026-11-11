# ADR-003 — El dashboard del terapeuta habla solo con la API

- **Estado:** aceptada (18/10/2026) · implementada, probada (copia de la BD real) y **verificada en el entorno del autor** (chat, Ollama, sesión real, Consola, clave e historial)
- **Decide:** Álvaro García · **Revisa:** Marcos Expósito
- **Afecta a:** arquitectura ([`arquitectura_v2.mmd`](../arquitectura_v2.mmd)), `docker-compose.yml`, `src/dashboard/`, memoria NF3 (arquitectura implementada vs diseñada, privacidad)

## Contexto
- **NF2 entregado:** el dashboard consume el backend por **REST JSON**; el plan de trabajo dice «Dashboard sobre la API (alerta, evolución longitudinal y consola editable)» y que depende del contrato de la API.
- **Stack hasta ahora:** el dashboard abría Postgres con SQLAlchemy (≈12 consultas SQL) y leía `metrics.json` del disco; solo usaba la API para `/health`.
- Consecuencias de ese desvío: las **correcciones del terapeuta** (historia 9) no tenían una vía segura —corregir una valoración obliga a recalcular `iniciativa` y las métricas de la sesión—, y el dashboard tenía acceso a datos sensibles (`nota_clinica`, textos) con credenciales de BD.

## Decisión
**Todo el dashboard pasa por la API** (lectura y escritura). El servicio `dashboard` ya no recibe cadena de conexión a Postgres ni monta el directorio del modelo.

| Necesidad del dashboard | Endpoint |
|---|---|
| Conteos y distribuciones de la cabecera | `GET /resumen` |
| Alumnos y sesiones | `GET /students`, `GET /sessions` (`?origen=`, `?student_id=`), `GET /sessions/by-student/{id}` |
| Predicciones y alerta operacional | `GET /predicciones` (por defecto, la última versión del modelo) |
| Métricas del modelo y anti-fuga | `GET /modelo/metricas` |
| Conversaciones reales y sus turnos | `GET /conversaciones`, `GET /conversaciones/{id}` |
| Una fila por figura (contrato `turn_data`) | `GET /conversaciones/{id}/figuras` (ADR-002) |
| **Corregir valoración de un turno** | `PATCH /conversaciones/{id}/turnos/{orden}` → recalcula la sesión |
| **Corregir etiqueta / nota clínica** | `PATCH /sessions/{id}/correccion`; la nota solo se devuelve en `GET /sessions/{id}` |
| Historial de correcciones | `GET /correcciones?session_id=&conversacion_id=` |
| ¿Hay predicción sobre sesiones reales? | `GET /students/{id}/prediccion` (puerta; hoy `disponible: false` y explica por qué) |
| Alumnos para la pantalla del menor | `GET /conversaciones/alumnos` (abierto, solo `student_id` y competencia) |

Reglas de negocio que quedan en el backend: valoración efectiva `COALESCE(accuracy_corregido, evaluacion)`, el original no se pierde, solo se corrigen conversaciones terminadas y turnos del menor con valoración, y las métricas se recalculan con la misma función que usa `metricas_reales --recalcular` (`metricas.recalcular_sesion`).

## Alternativas descartadas
- **Mantener la lectura directa y documentarlo.** Habría sido válido para la rúbrica (coherencia declarada), pero contradice lo entregado y deja las correcciones sin vía segura.
- **Híbrido (API para escribir, BD para leer).** Dos caminos de acceso a los datos y credenciales de BD en el dashboard: no reduce la superficie sensible.

## Consecuencias y límites (para la memoria, con honestidad)
- (+) El diagrama entregado y el sistema vuelven a coincidir; el contrato REST es la única interfaz del dashboard y un test falla si vuelve a abrir la BD.
- (+) Privacidad: `nota_clinica` no sale en los listados; el dashboard no tiene credenciales de BD.
- (±) **Autenticación de prototipo.** Todo el dashboard-API exige `X-API-Key` (`API_KEY_TERAPEUTA`; en compose es obligatoria, con clave de desarrollo por defecto). `/health`, `/`, `/chat` y el flujo del menor (`POST /conversaciones…`, `GET /conversaciones/alumnos`) siguen abiertos; `/health` informa de `auth_terapeuta: activa/desactivada`. Es **una clave compartida**: no hay usuarios, roles ni caducidad, y no basta para datos reales de menores. Debe constar entre las limitaciones.
- (−) **No se predice en línea.** El diseño habla de «carga del modelo desde FastAPI para predicción en cada sesión»; hoy las predicciones las calcula por lotes `train_classifier`. Sobre sesiones reales no se predice, y la puerta `GET /students/{id}/prediccion` lo declara: hacen falta 4 sesiones reales por alumno (hoy 1), `%DET` real es provisional y aMLU/PEPE/IRC dependen de un evaluador sin validar. Cuando esos motivos desaparezcan, `disponible` se abre sin tocar el endpoint.
- (−) Más tráfico JSON: el listado sintético completo pesa ≈0,9 MB (100 ms); suficiente para el prototipo, con caché de 20 s en el dashboard.
- (±) **Historial de correcciones** (`correccion_log`, migración 011): cada cambio real guarda autor, fecha, campo, valor anterior y nuevo; repetir un valor no genera filas; de la nota clínica solo consta que cambió. **El autor es el nombre declarado en `X-Terapeuta` y no está verificado**: sirve de rastro, no de prueba.

## Verificación
- Suite: **158 passed** (34 nuevas entre decisión 3, límites y hora peninsular): endpoints de lectura y de corrección, validaciones (404/409/422), dashboard completo con `AppTest` (arranque, corregir un turno y ver el PEPE recalculado, guardar etiqueta y nota, aviso si la API cae) y test que falla si el dashboard menciona SQLAlchemy, `DATABASE_URL`, `metrics.json` o el compose le da acceso a la BD.
- **Con una copia de la BD real del autor** (1500 sintéticas + 30 reales + 1200 predicciones), dashboard y API sin errores: carga completa en ≈3 s; `/sessions` sintético 857 KB en ≈0,1 s.

- **Límites corregidos (18/10/2026):** 15 pruebas nuevas (`test_limites.py`): 401 con/sin clave y endpoints abiertos, historial (autor, no-op, nota sin contenido, `X-Terapeuta` obligatorio), puerta de predicción (cerrada, se abre sola, ignora sintéticas), `guardar_predicciones` en `session_data`, `hubo_respuesta`. Sobre la copia de la BD real, con las migraciones 008→011 (y la vista 009 antigua sustituida por la nueva): `turn_data` sigue en `208 | 38`, backfill 1200/1500, dashboard sin errores con clave.
