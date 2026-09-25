$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

$Python = ".\.venv\Scripts\python.exe"
$BotTask = Get-ScheduledTask -TaskName "GOLIDE-Trading-Bot" -ErrorAction SilentlyContinue
$PanelTask = Get-ScheduledTask -TaskName "GOLIDE-Control-Panel" -ErrorAction SilentlyContinue
if (-not (Test-Path $Python) -or $null -eq $BotTask -or $null -eq $PanelTask) {
    & (Join-Path $PSScriptRoot "Install-Golide.ps1")
}
if (-not (Test-Path $Python)) { throw "The GOLIDE Python environment was not created." }

& $Python -m pip install -r requirements.txt
& $Python -m scripts.configure_demo_forward
& $Python -m scripts.install_fast_manager
& $Python -m pytest -q

Write-Host ""
Write-Host "Preparation passed. Do not start GOLIDE yet."
Write-Host "1. In MT5 Navigator, refresh Expert Advisors."
Write-Host "2. Attach GOLIDE/GolideFastManager to exactly ONE chart."
Write-Host "3. Leave InpDemoOnly=true and enable Algo Trading."
Write-Host "4. Then run: .\deploy\windows\Start-Golide.ps1"
Write-Host "5. Open http://127.0.0.1:8000 and click Resume Demo."
