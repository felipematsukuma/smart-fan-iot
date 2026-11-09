$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $taskRoot
try {
    & docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar infraestrutura para teste' }
    & docker compose run --rm --no-deps --pull never `
        -v "${taskRoot}/infra/tests:/tests:ro" `
        -v "${taskRoot}/secrets/rabbit_writer:/run/secrets/rabbit_writer:ro" `
        bootstrap python -m pytest /tests/test_reliability_integration.py -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Falha nos testes reais de entrega duravel' }
}
finally { Pop-Location }
