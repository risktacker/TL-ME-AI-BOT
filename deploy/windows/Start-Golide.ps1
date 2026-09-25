$ErrorActionPreference = "Stop"
Start-ScheduledTask -TaskName "GOLIDE-Control-Panel"
Start-ScheduledTask -TaskName "GOLIDE-Trading-Bot"
Write-Host "GOLIDE services started. Dashboard: http://127.0.0.1:8000"
