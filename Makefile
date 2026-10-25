.PHONY: up-simulado bateria metricas test smoke up down logs migrate seed train pipeline demo dashboard pull-model health verify reset

COMPOSE = docker compose -f environment/docker-compose.yml --env-file environment/.env

up:
	@test -f environment/.env || cp environment/.env.example environment/.env
	@mkdir -p src/models
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

# Descarga el modelo en el Ollama del HOST (el que usa el backend por defecto).
# Si usas el Ollama del compose (perfil ollama-local): docker compose --profile ollama-local exec ollama ollama pull <modelo>
pull-model:
	ollama pull $${OLLAMA_MODEL:-qwen3:14b}

# Aplica las migraciones SQL (idempotentes) sobre un volumen de Postgres ya existente.
migrate:
	@for f in data/init-db/*.sql; do echo "-> $$f"; $(COMPOSE) exec -T db sh -c 'psql -q -U $$POSTGRES_USER -d $$POSTGRES_DB' < $$f; done

# Carga el corpus sintético corregido (generador de Marcos) en Postgres, vaciando antes las tablas.
# Para el generador anterior (con turnos, pero filtra la etiqueta): make seed GENERADOR=heredado
GENERADOR ?= marcos
seed:
	$(COMPOSE) exec backend python -m scripts.seed_corpus --reset --generador $(GENERADOR)

# Entrena el clasificador (CV por alumno + anti-fuga), guarda src/models/ y escribe classifier_predictions.
train:
	$(COMPOSE) exec backend python -m scripts.train_classifier

# Calcula las métricas de las conversaciones reales terminadas y las compara con el corpus de entrenamiento.
metricas:
	$(COMPOSE) exec backend python -m scripts.metricas_reales

# Arranca el stack SIN LLM ni GPU: la valoración 0/1/2 la hacen reglas (docs/modo-simulado.md). Solo para ejecutar y demostrar.
up-simulado: export LLM_PROVIDER = simulado
up-simulado: up

# Tests de contrato (Ollama simulado, Postgres del stack). Instala pytest en el contenedor la primera vez.
test:
	$(COMPOSE) exec backend sh -c 'pip install -q -r requirements-dev.txt && python -m pytest'

# Prueba de humo REAL: una conversación completa contra tu Ollama, midiendo la latencia por turno.
smoke:
	$(COMPOSE) exec backend python -m scripts.smoke_conversacion --url http://localhost:8000

# Regresión del prompt de valoración 0/1/2 contra tu Ollama real (opcional, ~5-10 min): dos baterías de respuestas etiquetadas.
bateria:
	$(COMPOSE) exec backend python -m scripts.bateria_valoracion --detalle

# Carga corpus + entrena: deja el stack listo para visualizar.
pipeline: seed train

# Todo de cero: levanta, espera a la BD, carga corpus y entrena.
demo: up
	@echo "Esperando al backend..."; for i in $$(seq 1 30); do curl -sf http://localhost:$${BACKEND_PORT:-8010}/ >/dev/null && break; sleep 2; done
	$(MAKE) pipeline
	@echo "Dashboard: http://localhost:$${DASHBOARD_PORT:-8501}   API: http://localhost:$${BACKEND_PORT:-8010}/docs"

dashboard:
	@echo "http://localhost:$${DASHBOARD_PORT:-8501}"

health:
	curl -s http://localhost:$${BACKEND_PORT:-8010}/health | python3 -m json.tool

# Comprobación rápida de las etapas (conteos en BD + modelo guardado).
verify:
	$(COMPOSE) exec db sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB -c "SELECT (SELECT count(*) FROM student_profile_sim) alumnos, (SELECT count(*) FROM session_data) sesiones, (SELECT count(*) FROM classifier_predictions) predicciones;"'
	@test -f src/models/metrics.json && python3 -c "import json;m=json.load(open('src/models/metrics.json'));print(m['modelo_version'],'F1-macro',m['f1_macro'],'cumple',m['cumple_umbrales'],'anti-fuga',m['anti_fuga']['superado'])" || echo "Sin modelo: make train"

# Borra volúmenes (BD, modelos Ollama) para empezar limpio.
reset:
	$(COMPOSE) down -v
	rm -rf src/models
