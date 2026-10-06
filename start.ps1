# Codex Session Tracker launcher. Usage:  .\start.ps1  [-Port 8765] [-Foreground]
param([int]$Port = 8765, [switch]$Foreground)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$url  = "http://127.0.0.1:$Port/"

function Test-Up {
  try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "$($url)api/health").StatusCode -eq 200 } catch { $false }
}

if (Test-Up) { Write-Host "Already running at $url"; Start-Process $url; exit 0 }

$py = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python.exe).Source }

if ($Foreground) {
  & (Get-Command python.exe).Source "$here\server.py" --port $Port
  exit $LASTEXITCODE
}

$log = Join-Path $here 'tracker.log'
Start-Process -FilePath $py -ArgumentList @("`"$here\server.py`"", '--port', $Port, '--no-browser') `
  -WorkingDirectory $here -WindowStyle Hidden -RedirectStandardError $log
for ($i = 0; $i -lt 40 -and -not (Test-Up); $i++) { Start-Sleep -Milliseconds 250 }
if (Test-Up) { Write-Host "Codex Session Tracker running at $url  (stop with .\stop.ps1)"; Start-Process $url }
else { Write-Warning "Server did not start - see $log" ; exit 1 }
