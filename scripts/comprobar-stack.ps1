# Comprueba el stack de SOCIAL-SIM Chat. Ejecutar desde la raiz del repo:
#   powershell -ExecutionPolicy Bypass -File scripts\comprobar-stack.ps1
#   Opcional: -EsperadoTurnData "208|38" exige ese recuento exacto (filas|conversaciones) de la vista turn_data;
#   sin el, basta con que la vista sea accesible (0|0 es normal en una instalacion nueva).
param([string]$EsperadoTurnData = "")
$ErrorActionPreference = "Continue"
$compose = "environment/docker-compose.yml"
$envFile = "environment/.env"

function Leer-Env($nombre, $defecto) {
    if (Test-Path $envFile) {
        $l = Select-String -Path $envFile -Pattern "^\s*$nombre\s*=\s*(.+)$" | Select-Object -First 1
        if ($l) { return $l.Matches[0].Groups[1].Value.Trim() }
    }
    return $defecto
}
$clave   = Leer-Env "API_KEY_TERAPEUTA" "dev-terapeuta-local"
$pBack   = Leer-Env "BACKEND_PORT" "8010"
$pDash   = Leer-Env "DASHBOARD_PORT" "8501"
$modelo  = Leer-Env "OLLAMA_MODEL" "qwen3:14b"
$back    = "http://localhost:$pBack"

$script:fallos = 0
function Resultado($ok, $texto, $pista) {
    if ($ok) { Write-Host ("[ OK ] " + $texto) -ForegroundColor Green }
    else { Write-Host ("[FALLA] " + $texto) -ForegroundColor Red; if ($pista) { Write-Host ("        -> " + $pista) -ForegroundColor Yellow }; $script:fallos++ }
}
function Codigo($url, $cab) {
    try { return (Invoke-WebRequest -Uri $url -Headers $cab -UseBasicParsing -TimeoutSec 10).StatusCode }
    catch { if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode } else { return 0 } }
}
function Sql($consulta) {
    (docker compose -f $compose exec -T db psql -U social_sim -d social_sim_chat -t -A -c $consulta 2>&1) -join " "
}

Write-Host "`n== Contenedores ==" -ForegroundColor Cyan
$ps = docker compose -f $compose ps --format "{{.Service}} {{.State}}" 2>&1
$ps | ForEach-Object { Write-Host "   $_" }
foreach ($s in "db","backend","dashboard") {
    Resultado ([bool]($ps | Select-String "^$s running")) "contenedor $s en marcha" "docker compose -f $compose up -d"
}

Write-Host "`n== Ollama en Windows ==" -ForegroundColor Cyan
$tags = $null
try { $tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5 } catch {}
Resultado ($null -ne $tags) "Ollama responde en localhost:11434" "Abre Ollama (o 'ollama serve')"
if ($tags) {
    $nombres = $tags.models | ForEach-Object { $_.name }
    Resultado ($nombres -contains $modelo) "modelo $modelo descargado" "ollama pull $modelo   (instalados: $($nombres -join ', '))"
}
$hostOllama = [Environment]::GetEnvironmentVariable("OLLAMA_HOST","User")
if (-not $hostOllama) { $hostOllama = [Environment]::GetEnvironmentVariable("OLLAMA_HOST","Machine") }
Write-Host "   OLLAMA_HOST (variable de Windows): '$hostOllama'  (debe ser 0.0.0.0 para que el contenedor llegue)"
Write-Host "   Escuchando en el puerto 11434:"
Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ("     " + $_.LocalAddress) }
$desdeContenedor = (docker compose -f $compose exec -T backend python -c "import urllib.request as u;print(u.urlopen('http://host.docker.internal:11434/api/tags',timeout=8).status)" 2>&1) -join " "
Resultado ($desdeContenedor.Trim().EndsWith("200")) "el backend alcanza Ollama (host.docker.internal:11434)" "Pon OLLAMA_HOST=0.0.0.0, reinicia Ollama y permite el puerto 11434 en el Firewall de Windows. Detalle: $($desdeContenedor.Substring(0,[Math]::Min(150,$desdeContenedor.Length)))"

Write-Host "`n== API ==" -ForegroundColor Cyan
$h = $null
try { $h = Invoke-RestMethod -Uri "$back/health" -TimeoutSec 15 } catch {}
Resultado ($null -ne $h -and $h.database -eq "ok") "/health: base de datos ok" "docker compose -f $compose logs backend --tail 30"
if ($h) {
    Resultado ($h.status -eq "ok") "/health: estado general = $($h.status)" "Revisa el campo llm de /health"
    Resultado ($h.auth_terapeuta -eq "activa") "clave del terapeuta activa" "Define API_KEY_TERAPEUTA y reinicia el backend"
}
Resultado ((Codigo "$back/resumen" @{}) -eq 401) "/resumen sin clave -> 401" "El backend no recibio API_KEY_TERAPEUTA: restart backend"
Resultado ((Codigo "$back/resumen" @{ "X-API-Key" = "mala" }) -eq 401) "/resumen con clave mala -> 401" ""
Resultado ((Codigo "$back/resumen" @{ "X-API-Key" = $clave }) -eq 200) "/resumen con la clave correcta -> 200" "La clave de environment/.env no coincide con la del backend"
Resultado ((Codigo "$back/conversaciones/alumnos" @{}) -eq 200) "/conversaciones/alumnos abierto (pantalla del menor)" "Reinicia el backend: docker compose -f $compose restart backend"
Resultado ((Codigo "$back/chat/" @{}) -in 200,307) "/chat accesible" ""
Resultado ((Codigo "http://localhost:$pDash" @{}) -eq 200) "dashboard en http://localhost:$pDash" "docker compose -f $compose up -d --build dashboard"
$pg = $null
try { $pg = Invoke-RestMethod -Uri "$back/students/sim-001/prediccion" -Headers @{ "X-API-Key" = $clave } } catch {}
Resultado ($null -ne $pg -and $pg.disponible -eq $false) "puerta de prediccion real cerrada (esperado hoy)" "Revisa que el backend tenga el codigo nuevo"

Write-Host "`n== Base de datos ==" -ForegroundColor Cyan
$v = Sql "SELECT count(*) || '|' || count(DISTINCT conversacion_id) FROM turn_data;"
if ($EsperadoTurnData) { Resultado ($v.Trim() -eq $EsperadoTurnData) "turn_data = $v (esperado $EsperadoTurnData)" "Aplica 009, 010 y 011; si has hecho mas conversaciones el recuento sera mayor" }
else { Resultado ($v.Trim() -match '^\d+\|\d+$') "vista turn_data accesible (filas|conversaciones = $v; 0|0 es normal en una instalacion nueva)" "Aplica 009, 010 y 011" }
$t = Sql "SELECT count(*) FROM information_schema.columns WHERE table_name='session_data' AND column_name='turnos';"
Resultado ($t.Trim() -eq "0") "session_data sin columna turnos (migracion 012)" "Aplica 012_quitar_turnos_jsonb.sql"
$c = Sql "SELECT count(*) FROM information_schema.columns WHERE table_name='turn_data' AND column_name IN ('hubo_respuesta','es_prueba');"
Resultado ($c.Trim() -eq "2") "vista turn_data con hubo_respuesta y es_prueba" "Vuelve a aplicar 009_vista_turn_data.sql"
$p = Sql "SELECT count(*) || '|' || count(etiqueta_prediccion) FROM session_data WHERE origen='sintetico';"
Resultado ($p.Trim() -eq "1500|1200") "prediccion en session_data = $p (esperado 1500|1200)" "Aplica 010 o ejecuta make train"
$l = Sql "SELECT to_regclass('correccion_log');"
Resultado ($l.Trim() -eq "correccion_log") "tabla correccion_log existe" "Aplica 011_correccion_log.sql"
$o = Sql "SELECT origen || ':' || count(*) FROM session_data GROUP BY origen ORDER BY origen;"
Write-Host "   sesiones por origen: $o"

Write-Host ""
if ($script:fallos -eq 0) { Write-Host "TODO CORRECTO" -ForegroundColor Green } else { Write-Host "$($script:fallos) comprobacion(es) con fallo" -ForegroundColor Red }
