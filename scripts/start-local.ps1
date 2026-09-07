param([switch]$Production)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv/Scripts/python.exe'
if (!(Test-Path $python)) { throw 'Missing .venv. Follow README installation first.' }
if (!(Test-Path (Join-Path $root 'frontend/node_modules'))) { throw 'Run npm install in frontend first.' }
foreach ($port in @(8000, 3000)) {
  $probe = New-Object System.Net.Sockets.TcpClient
  try { $probe.Connect('127.0.0.1', $port); throw "Port $port is already in use. Stop the existing service first." }
  catch [System.Net.Sockets.SocketException] { }
  finally { $probe.Dispose() }
}
$backend = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $root -NoNewWindow -PassThru
try {
  $ready = $false
  $healthHeaders = @{}
  if ($env:GEO_BACKEND_TOKEN) { $healthHeaders.Authorization = "Bearer $env:GEO_BACKEND_TOKEN" }
  for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ($backend.HasExited) { throw 'Backend exited during startup.' }
    try { $health = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -Headers $healthHeaders -TimeoutSec 1; if ($health.status -eq 'ok') { $ready = $true; break } } catch { }
    Start-Sleep -Milliseconds 500
  }
  if (!$ready) { throw 'Backend health check timed out.' }
  Set-Location (Join-Path $root 'frontend')
  Write-Host 'GEO ready: http://127.0.0.1:3000 (Ctrl+C stops both services)'
  $mode = if ($Production) { 'start' } else { 'dev' }
  & node (Join-Path $root 'frontend/node_modules/next/dist/bin/next') $mode --hostname 127.0.0.1 --port 3000
} finally {
  if (!$backend.HasExited) { & taskkill.exe /PID $backend.Id /T /F | Out-Null }
}
