# DEV contour: auto-reloading server on port 8001 (the LIVE server stays on 8000).
# Develop here: edit code -> it reloads automatically -> poke http://127.0.0.1:8001
# When the feature is done: stop this (Ctrl+C), run scripts\check.ps1, then promote.
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = "utf-8"
Write-Host "DEV server -> http://127.0.0.1:8001  (auto-reload; Ctrl+C to stop)" -ForegroundColor Cyan
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001 --reload
