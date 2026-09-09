$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

if (-not (Test-Path ".venv")) { py -3.12 -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env. Set BOT_SYMBOL, DASHBOARD_TOKEN and demo safety flags before starting."
}

$User = "$env:USERDOMAIN\$env:USERNAME"
$BotAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Root\deploy\windows\Start-Bot.ps1`""
$PanelAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Root\deploy\windows\Start-Dashboard.ps1`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
$Settings = New-ScheduledTaskSettingsSet -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "GOLIDE-Trading-Bot" -Action $BotAction -Trigger $Trigger -Settings $Settings -User $User -RunLevel Highest -Force
Register-ScheduledTask -TaskName "GOLIDE-Control-Panel" -Action $PanelAction -Trigger $Trigger -Settings $Settings -User $User -RunLevel Highest -Force
Write-Host "Installed. Edit $Root\.env, open/login to MT5, then run Start-Golide.ps1."
