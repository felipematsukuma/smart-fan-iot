$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $taskRoot
try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File tools/bootstrap/bootstrap.ps1 -Start
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar API e credenciais' }
    & docker compose run --rm --no-deps --pull never `
        -v "${taskRoot}/infra/tests:/tests:ro" `
        -v "${taskRoot}/services/api/tests:/unit:ro" `
        bootstrap python -m pytest /tests/test_api_integration.py /unit -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Falha nos testes de autenticacao e API' }
    Push-Location (Join-Path $taskRoot 'web-smart-fan-iot/frontend')
    try {
        & npm run test:e2e
        if ($LASTEXITCODE -ne 0) { throw 'Falha no login/guards pelo navegador' }
    }
    finally { Pop-Location }
}
finally { Pop-Location }
