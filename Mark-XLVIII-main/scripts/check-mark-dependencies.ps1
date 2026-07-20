$ErrorActionPreference = "Stop"

$Modules = @(
    @{ Import = "PyQt6"; Package = "PyQt6" },
    @{ Import = "requests"; Package = "requests" },
    @{ Import = "google.genai"; Package = "google-genai" },
    @{ Import = "sounddevice"; Package = "sounddevice" },
    @{ Import = "comtypes"; Package = "comtypes" },
    @{ Import = "vosk"; Package = "vosk" },
    @{ Import = "miniaudio"; Package = "miniaudio" },
    @{ Import = "edge_tts"; Package = "edge-tts" },
    @{ Import = "snac"; Package = "snac" },
    @{ Import = "fastapi"; Package = "fastapi" },
    @{ Import = "uvicorn"; Package = "uvicorn[standard]" },
    @{ Import = "cryptography"; Package = "cryptography" },
    @{ Import = "psutil"; Package = "psutil" },
    @{ Import = "PIL"; Package = "pillow" },
    @{ Import = "cv2"; Package = "opencv-python" },
    @{ Import = "mss"; Package = "mss" }
)

$Missing = @()

foreach ($Module in $Modules) {
    $Name = $Module.Import
    $Code = "import importlib; importlib.import_module('$Name')"
    & python -c $Code 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] $Name"
    }
    else {
        Write-Host "[MISSING] $Name  (pip install $($Module.Package))"
        $Missing += $Module.Package
    }
}

if ($Missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Install missing dependencies with:"
    Write-Host "python -m pip install $($Missing -join ' ')"
    exit 1
}

Write-Host ""
Write-Host "All Mark runtime dependencies are importable."
