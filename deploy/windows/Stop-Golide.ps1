$ErrorActionPreference = "SilentlyContinue"
Stop-ScheduledTask -TaskName "GOLIDE-Trading-Bot"
Stop-ScheduledTask -TaskName "GOLIDE-Control-Panel"
Write-Host "GOLIDE services stopped. MT5 was not closed."
