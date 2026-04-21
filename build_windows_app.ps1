$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Virtual environment not found at $python"
}

Push-Location $projectRoot
try {
    & $python -m pip install -r requirements-build.txt
    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --name "VideoTranslationStudio" `
        --noconsole `
        --add-data "static;static" `
        --add-data ".env.example;." `
        launcher.py

    Write-Host "Build complete. Launch dist\\VideoTranslationStudio\\VideoTranslationStudio.exe"
} finally {
    Pop-Location
}
