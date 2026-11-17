$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$pythonExecutable = Join-Path $backendRoot '.venv\Scripts\python.exe'
# A Windows virtualenv launcher owns a second Python process. Stop the whole tree.
$launchers = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.ExecutablePath -eq $pythonExecutable -and $_.CommandLine -like '*uvicorn app.main:app*'
}
foreach ($launcher in $launchers) { & taskkill.exe /PID $launcher.ProcessId /T /F | Out-Null }
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if (-not (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue | Where-Object OwningProcess -ne 0)) { break }
    Start-Sleep -Milliseconds 250
}
if (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue | Where-Object OwningProcess -ne 0) {
    throw 'Port 8001 is still occupied. Backend was not restarted.'
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$server = Start-Process -FilePath $pythonExecutable -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8001' -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $backendRoot "data/server-$stamp.log") -RedirectStandardError (Join-Path $backendRoot "data/server-$stamp-error.log")
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ($server.HasExited) { throw 'Backend exited during startup. Check the latest server error log.' }
    try {
        $response = Invoke-WebRequest 'http://127.0.0.1:8001/salons/glow-studio' -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { Write-Host 'Backend restarted and responding on http://127.0.0.1:8001'; exit 0 }
    } catch { Start-Sleep -Milliseconds 250 }
}
throw 'Backend did not become ready. Check the latest server error log.'
