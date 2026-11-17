$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$pythonExecutable = Join-Path $backendRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Install backend dependencies first; see README.md.' }

# Start backend detached so it survives this shell.
$backendJob = Start-Job -ScriptBlock {
    param($python, $root)
    Set-Location $root
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
} -ArgumentList $pythonExecutable, $backendRoot

# Start frontend detached.
$frontendJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location $root
    & npm.cmd run dev
} -ArgumentList $projectRoot

Start-Sleep -Seconds 6
Write-Host "Backend job : $($backendJob.Id)"
Write-Host "Frontend job: $($frontendJob.Id)"
Write-Host ""
Write-Host "Salon:   http://127.0.0.1:3000"
Write-Host "Settings: http://127.0.0.1:3000/settings"
Write-Host "API docs: http://127.0.0.1:8001/docs"