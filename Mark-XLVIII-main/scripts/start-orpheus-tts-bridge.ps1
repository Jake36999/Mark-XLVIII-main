$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BridgeRoot = Join-Path $RepoRoot "tools\Orpheus-FastAPI-LMStudio"

if (-not (Test-Path -LiteralPath $BridgeRoot)) {
    throw "Orpheus bridge repo not found at $BridgeRoot"
}

$PreferredCudaPython = "F:\network_management\Wi-Fi Sensing & CSI Data Extraction\Model_training\.venv-gtx1080\Scripts\python.exe"
$RepoPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if ($env:ORPHEUS_PYTHON_EXE) {
    $PythonExe = $env:ORPHEUS_PYTHON_EXE
}
elseif (Test-Path -LiteralPath $PreferredCudaPython) {
    $PythonExe = $PreferredCudaPython
}
elseif (Test-Path -LiteralPath $RepoPython) {
    $PythonExe = $RepoPython
}
else {
    $PythonExe = "python"
}

$env:ORPHEUS_API_URL = if ($env:ORPHEUS_API_URL) { $env:ORPHEUS_API_URL } else { "http://127.0.0.1:1234/v1/completions" }
$env:ORPHEUS_MODEL_ID = if ($env:ORPHEUS_MODEL_ID) { $env:ORPHEUS_MODEL_ID } else { "orpeus_text_to_speech" }
$env:ORPHEUS_API_TIMEOUT = if ($env:ORPHEUS_API_TIMEOUT) { $env:ORPHEUS_API_TIMEOUT } else { "180" }
$env:ORPHEUS_PORT = if ($env:ORPHEUS_PORT) { $env:ORPHEUS_PORT } else { "5006" }
$env:ORPHEUS_CONCURRENCY = "1"
$env:ORPHEUS_MAX_RETRIES = "1"
$env:ORPHEUS_MAX_TOKENS = if ($env:ORPHEUS_MAX_TOKENS) { $env:ORPHEUS_MAX_TOKENS } else { "1200" }
$env:ORPHEUS_MIN_TOKENS = if ($env:ORPHEUS_MIN_TOKENS) { $env:ORPHEUS_MIN_TOKENS } else { "240" }
$env:ORPHEUS_TOKENS_PER_CHAR = if ($env:ORPHEUS_TOKENS_PER_CHAR) { $env:ORPHEUS_TOKENS_PER_CHAR } else { "5" }
$env:ORPHEUS_MAX_GENERATION_SECONDS = if ($env:ORPHEUS_MAX_GENERATION_SECONDS) { $env:ORPHEUS_MAX_GENERATION_SECONDS } else { "180" }
$env:CUDA_VISIBLE_DEVICES = if ($env:CUDA_VISIBLE_DEVICES) { $env:CUDA_VISIBLE_DEVICES } else { "0" }

Set-Location $BridgeRoot
Write-Host "Starting Orpheus TTS bridge on http://127.0.0.1:$env:ORPHEUS_PORT ..."
Write-Host "Python: $PythonExe"
Write-Host "CUDA_VISIBLE_DEVICES: $env:CUDA_VISIBLE_DEVICES"
Write-Host "LM Studio completions: $env:ORPHEUS_API_URL"
Write-Host "LM Studio TTS model: $env:ORPHEUS_MODEL_ID"
Write-Host "Synthesis concurrency: $env:ORPHEUS_CONCURRENCY"
Write-Host "Per-chunk limits: $env:ORPHEUS_MAX_TOKENS tokens / $env:ORPHEUS_MAX_GENERATION_SECONDS seconds"
& $PythonExe .\app.py
