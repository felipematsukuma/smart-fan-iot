$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $taskRoot
try {
    & docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Simulador nao ficou pronto' }
    $readinessTimer = [System.Diagnostics.Stopwatch]::StartNew()
    do {
        $simulatorStatus = & docker compose ps --format json simulator | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao consultar prontidao do simulador' }
        if ($simulatorStatus.Health -eq 'healthy') { break }
        Start-Sleep -Milliseconds 500
    } while ($readinessTimer.Elapsed.TotalSeconds -lt 60)
    if ($simulatorStatus.Health -ne 'healthy') { throw 'Timeout na prontidao MQTT/spool do simulador' }
    & docker compose run --rm --no-deps --pull never `
        -v "${taskRoot}/infra/tests:/tests:ro" `
        -v "${taskRoot}/secrets/mqtt_gateway:/run/secrets/mqtt_gateway:ro" `
        -v "${taskRoot}/secrets/rabbit_gateway:/run/secrets/rabbit_gateway:ro" `
        bootstrap python -m pytest /tests/test_simulator_integration.py -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Integracao MQTT do simulador falhou' }
}
finally { Pop-Location }
