$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $taskRoot
try {
    & docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar dependencias da cena' }
    & docker compose build frontend
    if ($LASTEXITCODE -ne 0) { throw 'Falha no build da cena' }
    & docker compose up -d --no-deps frontend
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao iniciar frontend' }
    Push-Location (Join-Path $taskRoot 'web-smart-fan-iot/frontend')
    try {
        & npx playwright test e2e/scene.spec.ts
        if ($LASTEXITCODE -ne 0) { throw 'Falha no fluxo 3D pelo navegador' }
    }
    finally { Pop-Location }
}
finally { Pop-Location }
