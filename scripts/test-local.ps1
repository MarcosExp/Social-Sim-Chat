<#
.SYNOPSIS
  Tests de contrato y prueba de humo real de la conversación (equivalente a `make test` / `make smoke`).
.DESCRIPTION
  Desde la raíz del repo, con el stack levantado:
      powershell -ExecutionPolicy Bypass -File scripts\test-local.ps1            # tests (Ollama simulado)
      powershell -ExecutionPolicy Bypass -File scripts\test-local.ps1 -Humo      # conversación real + latencias
      powershell -ExecutionPolicy Bypass -File scripts\test-local.ps1 -Metricas  # métricas de sesiones reales vs. corpus
#>
param([switch]$Humo, [switch]$Metricas)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$c = @('compose', '-f', 'environment/docker-compose.yml', '--env-file', 'environment/.env')
if ($Metricas) {
    & docker @c exec backend python -m scripts.metricas_reales
} elseif ($Humo) {
    & docker @c exec backend python -m scripts.smoke_conversacion --url http://localhost:8000
} else {
    & docker @c exec backend sh -c 'pip install -q -r requirements-dev.txt -c constraints.txt && python -m pytest'
}
exit $LASTEXITCODE
