$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "operator-env.ps1")

$PythonExe = Join-Path $env:MARK_OPERATOR_MARK_ROOT ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = "python"
}

Set-Location $env:MARK_OPERATOR_MARK_ROOT
Write-Host "Starting Mark XLVIII operator assistant ..."
& $PythonExe .\main.py
