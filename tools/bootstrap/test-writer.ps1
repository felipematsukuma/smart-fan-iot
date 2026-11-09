$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $taskRoot
try {
    & docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar gravador' }
    & docker compose run --rm --no-deps --pull never `
        -v "${taskRoot}/infra/tests:/tests:ro" `
        -v "${taskRoot}/secrets/rabbit_writer:/run/secrets/rabbit_writer:ro" `
        bootstrap python -m pytest /tests/test_writer_integration.py /tests/test_reliability_integration.py /tests/test_gateway_integration.py -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Falha nas integracoes reais do gravador' }
}
finally { Pop-Location }
