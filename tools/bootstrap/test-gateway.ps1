$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $taskRoot
try {
    & docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar gateway' }
    $deadline = (Get-Date).AddSeconds(60)
    do {
        $state = & docker inspect smartfan-aiot-gateway-1 --format '{{.State.Health.Status}}'
        if ($state -eq 'healthy') { break }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    if ($state -ne 'healthy') { throw 'Gateway nao ficou pronto' }
    & docker compose run --rm --no-deps --pull never `
        -v "${taskRoot}/infra/tests:/tests:ro" `
        -v "${taskRoot}/secrets/rabbit_writer:/run/secrets/rabbit_writer:ro" `
        bootstrap python -m pytest /tests/test_reliability_integration.py /tests/test_gateway_integration.py -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Falha nos testes de contrato e durabilidade' }
    & docker compose run --rm --no-deps --pull never `
        -v "${taskRoot}/infra/tests:/tests:ro" `
        -v "${taskRoot}/secrets/rabbit_api:/run/secrets/rabbit_api:ro" `
        -v "${taskRoot}/secrets/mqtt_gateway:/run/secrets/mqtt_gateway:ro" `
        bootstrap python -m pytest /tests/test_gateway_runtime.py -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Falha no percurso real do comando' }
}
finally { Pop-Location }
