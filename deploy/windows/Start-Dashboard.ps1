$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
while ($true) {
    & ".\.venv\Scripts\python.exe" -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8000 *>> "logs\dashboard.log"
    Start-Sleep -Seconds 10
}
