#!/bin/sh
# Prepara environment/.env: lo crea desde .env.example si falta y, si API_KEY_TERAPEUTA está vacía, genera una clave aleatoria.
# Lo usan `make up` y `scripts/setup-local.sh`. No toca una clave ya definida (ni siquiera la de desarrollo de versiones anteriores,
# que solo se avisa en el log del backend). Equivalente en Windows: la función Asegurar-Env de scripts/setup-local.ps1.
set -eu
cd "$(dirname "$0")/.."
ENV_FILE=environment/.env
[ -f "$ENV_FILE" ] || { cp environment/.env.example "$ENV_FILE"; echo "Creado $ENV_FILE"; }
if ! grep -Eq '^API_KEY_TERAPEUTA=[^[:space:]]+' "$ENV_FILE"; then
  clave=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')
  if grep -q '^API_KEY_TERAPEUTA=' "$ENV_FILE"; then
    sed -i.bak "s|^API_KEY_TERAPEUTA=.*|API_KEY_TERAPEUTA=$clave|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  else
    printf '\nAPI_KEY_TERAPEUTA=%s\n' "$clave" >> "$ENV_FILE"
  fi
  echo "Generada una clave aleatoria del terapeuta en $ENV_FILE"
fi
