# SOCIAL-SIM Chat

Entrenador conversacional y learning analytics para menores con TEA/Asperger (6-12 años).

Proyecto del Módulo C088 · Proyecto de Inteligencia Artificial y Big Data · Curso 2026–2027.

## Objetivo

Construir un entrenador conversacional con IA local que practique habilidades pragmáticas (metáforas, sarcasmo, deixis, preguntas) con el menor, registre cada interacción y ofrezca al terapeuta un panel con alertas tempranas de estancamiento. Todo el dato se procesa en local, sin nube.

El prototipo trabaja exclusivamente con **datos sintéticos**: valida que el sistema funciona de extremo a extremo, no su validez clínica.

## Equipo

- Álvaro García Puche — Dominio pedagógico, datos y dashboard
- Marcos Expósito Flox — Plataforma e ingeniería ML

## Stack

Python · FastAPI · Ollama (LLM local) · PostgreSQL · scikit-learn · Streamlit · Docker Compose

## Organización del repositorio

```
docs/          Documentación del proyecto y entregas
  adr/         Registro de decisiones de arquitectura
src/           Código fuente
data/          Datos sintéticos generados (no se versionan)
environment/   docker-compose y .env.example
tests/         Tests automáticos
```

## Cómo ejecutarlo

En construcción. El objetivo es que el prototipo se levante con un solo comando (`docker compose up`) e incluya un modo de LLM simulado para ejecutarlo sin GPU.

## Forma de trabajo

- Nada se sube a `main` sin pull request revisada por el otro miembro.
- Cada tarea tiene una issue asignada.
- Las decisiones técnicas relevantes se documentan en `docs/adr/`.

## Estado

NF1 — Presentación y viabilidad (entrega 22/09/2026).
