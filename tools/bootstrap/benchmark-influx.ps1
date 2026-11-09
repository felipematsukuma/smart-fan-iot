$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $taskRoot
try {
    & docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar ensaio InfluxDB' }
    & docker compose run --rm --no-deps --pull never bootstrap python -m infra.benchmark_influx
    if ($LASTEXITCODE -ne 0) { throw 'Falha no ensaio de capacidade InfluxDB' }
}
finally { Pop-Location }
