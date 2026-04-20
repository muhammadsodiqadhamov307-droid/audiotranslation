$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$ffmpegBin = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
$stdoutLog = Join-Path $projectRoot "uvicorn.out.log"
$stderrLog = Join-Path $projectRoot "uvicorn.err.log"

if (Test-Path $ffmpegBin) {
    $env:Path = "$ffmpegBin;$env:Path"
}

Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -WindowStyle Hidden

Write-Host "Server started in the background: http://127.0.0.1:8000"
Write-Host "Logs: $stdoutLog and $stderrLog"
