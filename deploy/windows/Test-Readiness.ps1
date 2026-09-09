$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root
$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Run Install-Golide.ps1 first." }
if (-not (Test-Path ".env")) { throw "Missing .env configuration." }
& $Python -m pytest -q
& $Python -m compileall -q .
& $Python -c "import MetaTrader5, fastapi, uvicorn; print('Packages ready')"
Write-Host "Code and packages are ready. MT5 demo connectivity remains the final smoke test."
