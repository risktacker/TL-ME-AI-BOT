$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
while ($true) {
    & ".\.venv\Scripts\python.exe" -m bot.main --mode demo *>> "logs\bot-supervisor.log"
    Start-Sleep -Seconds 15
}
