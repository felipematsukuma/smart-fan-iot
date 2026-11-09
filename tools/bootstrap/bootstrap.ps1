param([switch]$Start)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$secretRoot = Join-Path $root 'secrets'
if (-not (Test-Path -LiteralPath $secretRoot)) {
    New-Item -ItemType Directory -Path $secretRoot | Out-Null
}
if ($env:OS -eq 'Windows_NT') {
    $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls $secretRoot /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao proteger a pasta local de segredos' }
}
$pythonExe = Join-Path $root 'web-smart-fan-iot/backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { $pythonExe = (Get-Command python).Source }
& $pythonExe (Join-Path $root 'infra/prepare.py')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar credenciais locais' }
& docker compose -f (Join-Path $root 'compose.yaml') config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Configuracao Compose invalida' }
if ($Start) {
    & docker compose -f (Join-Path $root 'compose.yaml') up --build -d
    if ($LASTEXITCODE -ne 0) { throw 'Falha na subida da infraestrutura' }
}
