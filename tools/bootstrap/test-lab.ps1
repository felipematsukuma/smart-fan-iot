$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $taskRoot
try {
    & docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar laboratorio' }
    & docker compose -f compose.yaml -f infra/compose.test.yaml run --rm --no-deps --pull never `
        -v "${taskRoot}/infra/tests:/tests:ro" `
        -v "${taskRoot}/secrets/rabbit_api-monitor:/run/secrets/rabbit_api-monitor:ro" `
        bootstrap python -m pytest /tests/test_lab_integration.py /tests/test_messaging_integration.py /tests/test_control_integration.py /tests/test_devices_integration.py /tests/test_api_integration.py /tests/test_realtime_integration.py /tests/test_gateway_integration.py -q -p no:cacheprovider --tb=short
    if ($LASTEXITCODE -ne 0) { throw 'Falha nas integracoes do laboratorio' }
    Push-Location (Join-Path $taskRoot 'web-smart-fan-iot/frontend')
    try {
        & npm run test:e2e
        if ($LASTEXITCODE -ne 0) { throw 'Falha no laboratorio pelo navegador' }
    }
    finally { Pop-Location }
}
finally { Pop-Location }
