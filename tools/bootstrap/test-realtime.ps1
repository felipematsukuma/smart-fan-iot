$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $taskRoot
try {
    & docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar tempo real' }
    & docker compose run --rm --no-deps --pull never `
        -v "${taskRoot}/infra/tests:/tests:ro" `
        -v "${taskRoot}/secrets/rabbit_inference:/run/secrets/rabbit_inference:ro" `
        bootstrap python -m pytest /tests/test_realtime_integration.py /tests/test_realtime_runtime.py /tests/test_writer_integration.py -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Falha nas integracoes de tempo real/historico' }
    Push-Location (Join-Path $taskRoot 'web-smart-fan-iot/frontend')
    try {
        & npm run test:e2e
        if ($LASTEXITCODE -ne 0) { throw 'Falha no percurso real pelo navegador' }
    }
    finally { Pop-Location }
}
finally { Pop-Location }
