#!/usr/bin/env bash
# Instala y arranca el stack local de SOCIAL-SIM Chat (Linux / macOS / WSL).
# Descarga imágenes Docker y el modelo LLM, levanta los servicios, carga el corpus y entrena el clasificador.
# Idempotente. Uso (desde cualquier carpeta):  bash scripts/setup-local.sh [--sin-modelo] [--reset]
set -euo pipefail
cd "$(dirname "$0")/.."

SIN_MODELO=0; RESET=0
for a in "$@"; do case "$a" in --sin-modelo) SIN_MODELO=1;; --reset) RESET=1;; *) echo "Opción desconocida: $a"; exit 2;; esac; done


echo "==> Comprobando Docker"
command -v docker >/dev/null || { echo "Docker no está instalado."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker no responde: arranca Docker (Desktop o servicio) y repite."; exit 1; }

[ -f environment/.env ] || { cp environment/.env.example environment/.env; echo "Creado environment/.env"; }
mkdir -p src/models
get() { grep -E "^$1=" environment/.env | head -1 | cut -d= -f2- | tr -d '\r' || true; }
MODEL="$(get OLLAMA_MODEL)"; MODEL="${MODEL:-qwen3:14b}"
OHOST="$(get OLLAMA_URL)"; OHOST="${OHOST:-http://host.docker.internal:11434}"
PORT="$(get BACKEND_PORT)"; PORT="${PORT:-8010}"
# Ollama del compose (opcional) solo si OLLAMA_URL apunta al servicio `ollama`; por defecto se usa el del host.
BUNDLED=0; echo "$OHOST" | grep -Eq '^https?://ollama(:|/|$)' && BUNDLED=1
PROFILE=(); [ "$BUNDLED" = 1 ] && PROFILE=(--profile ollama-local)
C=(docker compose "${PROFILE[@]}" -f environment/docker-compose.yml --env-file environment/.env)
DPORT="$(get DASHBOARD_PORT)"; DPORT="${DPORT:-8501}"

if [ "$RESET" = 1 ]; then echo "==> Reset: borrando volúmenes"; "${C[@]}" down -v; rm -rf src/models; mkdir -p src/models; fi

echo "==> Descargando imágenes"; if [ "$BUNDLED" = 1 ]; then "${C[@]}" pull db ollama; else "${C[@]}" pull db; fi
echo "==> Construyendo backend y dashboard (descarga dependencias Python)"; "${C[@]}" build
echo "==> Levantando servicios"; "${C[@]}" up -d

echo "==> Esperando al backend"
for i in $(seq 1 60); do curl -sf "http://localhost:$PORT/" >/dev/null && break; sleep 2; [ "$i" = 60 ] && { echo "El backend no responde: ${C[*]} logs backend"; exit 1; }; done

echo "==> Aplicando migraciones SQL (idempotentes)"
for f in data/init-db/*.sql; do echo "  -> $f"; "${C[@]}" exec -T db sh -c 'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$f"; done

if [ "$SIN_MODELO" = 0 ]; then
  if [ "$BUNDLED" = 1 ]; then
    echo "==> Descargando modelo '$MODEL' en el Ollama del compose (solo la primera vez)"; "${C[@]}" exec ollama ollama pull "$MODEL"
  else
    PROBE="$(echo "$OHOST" | sed 's/host\.docker\.internal/localhost/')"; PROBE="${PROBE%/}"
    if TAGS="$(curl -sf --max-time 5 "$PROBE/api/tags")"; then
      if echo "$TAGS" | grep -q "\"name\":\"$MODEL\"\|\"name\":\"$MODEL:latest\""; then echo "Modelo '$MODEL' ya disponible en Ollama."
      elif command -v ollama >/dev/null; then echo "==> ollama pull $MODEL"; ollama pull "$MODEL"
      else echo "Falta el modelo '$MODEL': descárgalo con  ollama pull $MODEL"; fi
    else echo "No responde Ollama en $PROBE: arráncalo (o cambia OLLAMA_URL en environment/.env)."; fi
  fi
else echo "Modelo LLM omitido (--sin-modelo)."; fi

echo "==> Cargando corpus sintético"; "${C[@]}" exec backend python -m scripts.seed_corpus --reset
echo "==> Entrenando clasificador"; "${C[@]}" exec backend python -m scripts.train_classifier

echo; echo "Listo."; echo "  Dashboard : http://localhost:$DPORT"; echo "  API       : http://localhost:$PORT/docs"
