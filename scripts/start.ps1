$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$pythonExecutable = Join-Path $backendRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Install backend dependencies first; see README.md.' }
$backendProcess = Start-Process -FilePath $pythonExecutable -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8001') -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru
try {
    Set-Location -LiteralPath $projectRoot
    Write-Host 'Salon: http://127.0.0.1:3000 | Settings: http://127.0.0.1:3000/settings'
    & npm.cmd run dev
} finally {
    if (-not $backendProcess.HasExited) { Stop-Process -Id $backendProcess.Id }
}
