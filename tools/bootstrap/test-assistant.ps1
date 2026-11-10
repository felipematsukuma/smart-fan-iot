$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $taskRoot
try {
    & docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar assistente' }
    & docker compose -f compose.yaml -f infra/compose.test.yaml run --rm --no-deps --pull never `
        -v "${taskRoot}/infra/tests:/tests:ro" bootstrap python -m pytest `
        /tests/test_assistant_integration.py /tests/test_api_integration.py /tests/test_lab_integration.py -q -p no:cacheprovider --tb=short
    if ($LASTEXITCODE -ne 0) { throw 'Falha nas integracoes de assistente' }
    Push-Location (Join-Path $taskRoot 'web-smart-fan-iot/frontend')
    try {
        & npx playwright test e2e/assistant.spec.ts
        if ($LASTEXITCODE -ne 0) { throw 'Falha no streaming local pelo navegador' }
    }
    finally { Pop-Location }
}
finally { Pop-Location }
