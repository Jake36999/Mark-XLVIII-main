$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "operator-env.ps1")

$DaemonRoot = Join-Path $env:MARK_OPERATOR_AGENT_BACKEND_ROOT "backend\python-daemon"
if (-not (Test-Path -LiteralPath $DaemonRoot)) {
    throw "Aletheia daemon root not found: $DaemonRoot"
}

$PythonExe = Join-Path $DaemonRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = "python"
}

Set-Location $DaemonRoot
Write-Host "Starting Aletheia daemon on $env:ALETHEIA_BRIDGE_HOST`:$env:ALETHEIA_BRIDGE_PORT ..."
& $PythonExe -m orchestrator.main
