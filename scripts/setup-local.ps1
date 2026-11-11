<#
.SYNOPSIS
  Instala y arranca el stack local de SOCIAL-SIM Chat en Windows (sin necesitar `make`).
.DESCRIPTION
  Descarga imágenes Docker y el modelo LLM, levanta Postgres + Ollama + backend + dashboard,
  carga el corpus sintético y entrena el clasificador. Idempotente: puedes repetirlo.
  Requisito: Docker Desktop en marcha. Ejecutar desde la raíz del repo:
      powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1
.PARAMETER SinModelo
  No descarga el modelo de Ollama (~9 GB). El resto del stack funciona igual.
.PARAMETER Reset
  Borra volúmenes (BD y modelos descargados) antes de empezar.
#>
param([switch]$SinModelo, [switch]$Reset)
$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)   # los .sql llevan tildes
Set-Location (Split-Path -Parent $PSScriptRoot)

$script:profileArgs = @()
function Compose { & docker compose @script:profileArgs -f environment/docker-compose.yml --env-file environment/.env @args; if ($LASTEXITCODE -ne 0) { throw "Falló: docker compose $($args -join ' ')" } }

Write-Host "==> Comprobando Docker" -ForegroundColor Cyan
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker no está instalado. Instala Docker Desktop y vuelve a ejecutar." }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker no responde. Abre Docker Desktop, espera a que arranque y repite." }

if (-not (Test-Path environment/.env)) { Copy-Item environment/.env.example environment/.env; Write-Host "Creado environment/.env" }
New-Item -ItemType Directory -Force src/models | Out-Null
$envText = Get-Content environment/.env -Raw
$model = if ($envText -match '(?m)^OLLAMA_MODEL=(.+)$') { $Matches[1].Trim() } else { 'qwen3:14b' }
$ollamaHost = if ($envText -match '(?m)^OLLAMA_URL=(.+)$') { $Matches[1].Trim() } else { 'http://host.docker.internal:11434' }
$port = if ($envText -match '(?m)^BACKEND_PORT=(\d+)') { $Matches[1] } else { '8010' }
# Ollama del compose (opcional) solo si OLLAMA_URL apunta al servicio `ollama`; por defecto se usa el del host.
$bundled = $ollamaHost -match '^https?://ollama(:|/|$)'
if ($bundled) { $script:profileArgs = @('--profile', 'ollama-local') }
$dport = if ($envText -match '(?m)^DASHBOARD_PORT=(\d+)') { $Matches[1] } else { '8501' }

if ($Reset) { Write-Host "==> Reset: borrando volúmenes" -ForegroundColor Yellow; Compose down -v; Remove-Item -Recurse -Force src/models -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Force src/models | Out-Null }

Write-Host "==> Descargando imágenes (postgres, ollama, python)" -ForegroundColor Cyan
if ($bundled) { Compose pull db ollama } else { Compose pull db }
Write-Host "==> Construyendo backend y dashboard (descarga dependencias Python)" -ForegroundColor Cyan
Compose build
Write-Host "==> Levantando servicios" -ForegroundColor Cyan
Compose up -d

Write-Host "==> Esperando al backend" -ForegroundColor Cyan
# 127.0.0.1 y no localhost: en Windows PowerShell 5.1 localhost prueba antes ::1 y pierde ~2 s por intento con los puertos ligados a 127.0.0.1
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/" -TimeoutSec 5 | Out-Null; $ok = $true; break } catch { Start-Sleep 2 }
}
if (-not $ok) { throw "El backend no responde. Revisa: docker compose -f environment/docker-compose.yml logs backend" }

Write-Host "==> Aplicando migraciones SQL (idempotentes)" -ForegroundColor Cyan
foreach ($f in Get-ChildItem data/init-db/*.sql | Sort-Object Name) {
    Get-Content $f.FullName -Raw -Encoding UTF8 | docker compose -f environment/docker-compose.yml --env-file environment/.env exec -T db sh -c 'psql -q -U $POSTGRES_USER -d $POSTGRES_DB'
    if ($LASTEXITCODE -ne 0) { throw "Falló la migración $($f.Name)" }
}

if (-not $SinModelo) {
    if ($bundled) {
        Write-Host "==> Descargando modelo '$model' en el Ollama del compose (solo la primera vez)" -ForegroundColor Cyan
        Compose exec ollama ollama pull $model
    } else {
        # Ollama en el host: se comprueba desde el host (localhost) que responde y tiene el modelo.
        $probe = ($ollamaHost -replace 'host\.docker\.internal', 'localhost').TrimEnd('/')
        try {
            $names = (Invoke-RestMethod "$probe/api/tags" -TimeoutSec 5).models.name
            if ($names -contains $model -or $names -contains "${model}:latest") { Write-Host "Modelo '$model' ya disponible en Ollama." -ForegroundColor Green }
            elseif (Get-Command ollama -ErrorAction SilentlyContinue) { Write-Host "==> ollama pull $model" -ForegroundColor Cyan; & ollama pull $model }
            else { Write-Host "Falta el modelo '$model' en Ollama y no encuentro el comando ollama: descárgalo con  ollama pull $model" -ForegroundColor Yellow }
        } catch { Write-Host "No responde Ollama en ${probe} - arráncalo (o cambia OLLAMA_URL en environment/.env)." -ForegroundColor Yellow }
    }
} else { Write-Host "Modelo LLM omitido (-SinModelo)." -ForegroundColor Yellow }

Write-Host "==> Cargando corpus sintético" -ForegroundColor Cyan
Compose exec backend python -m scripts.seed_corpus --reset
Write-Host "==> Entrenando clasificador" -ForegroundColor Cyan
Compose exec backend python -m scripts.train_classifier

Write-Host ""
Write-Host "Listo." -ForegroundColor Green
Write-Host "  Dashboard : http://localhost:$dport"
Write-Host "  API       : http://localhost:$port/docs"
