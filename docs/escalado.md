# Escalado: de PostgreSQL a Kafka + Spark (diseño, no implementado)

Estado: **documentado, no implementado.** El prototipo usa PostgreSQL 16 como único almacén; es la decisión del NF2
(sección 5 de aquella memoria) y la que se construye, se prueba y se reproduce en este repositorio.

## Volumen actual

100 alumnos, 1.500 sesiones, 1.200 predicciones, 26.534 filas en `conversacion_turno` y 7.875 en la vista `turn_data`
(corpus sintético, migración 013). Con ese volumen PostgreSQL 16 sobra; Kafka y Spark añadirían servicios sin ganancia medible.

## Diseño de escalado (sin cifras medidas)

1. La API escribe cada turno en un tema de Kafka (clave: `session_id`, para conservar el orden dentro de la sesión).
2. Un trabajo de Spark Structured Streaming calcula las cinco métricas por sesión y las features de ventana y las escribe
   en PostgreSQL (`session_data`).
3. El entrenamiento del clasificador sigue por lotes, leyendo de PostgreSQL.
4. El dashboard no cambia: solo habla con la API ([ADR-003](adr/ADR-003_dashboard_solo_por_api.md)).

## Qué habría que medir antes de adoptarlo

- El coste de recalcular las métricas al terminar cada sesión.
- El coste de la vista `turn_data` con muchos más alumnos.
- Si el almacén único sigue aguantando la escritura de turnos en paralelo.

## Por qué no ahora

Añadiría servicios al compose (más imágenes que fijar por digest), cambiaría el cálculo de las métricas y no mejora nada con
este volumen. Es una ampliación futura, separada de lo construido.
