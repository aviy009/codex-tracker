# Stops the Codex Session Tracker server started by start.ps1
$procs = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
  Where-Object { $_.CommandLine -like '*codex-tracker*server.py*' }
if (-not $procs) { Write-Host 'Not running.'; exit 0 }
$procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host "Stopped PID $($_.ProcessId)" }
