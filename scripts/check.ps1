# Test-contour GATE: unit tests + in-process API smoke test.
# GREEN = safe to promote to the live server (scripts\serve_live.ps1).
# RED   = do NOT restart live; fix the failures first.
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = "utf-8"

Write-Host "`n[1/2] pytest ..." -ForegroundColor Cyan
python -m pytest -q
$pytest_ok = ($LASTEXITCODE -eq 0)

Write-Host "`n[2/2] smoke test (in-process API) ..." -ForegroundColor Cyan
python scripts\smoke_test.py
$smoke_ok = ($LASTEXITCODE -eq 0)

Write-Host ""
if ($pytest_ok -and $smoke_ok) {
    Write-Host "GREEN - tests + smoke passed. Safe to promote: scripts\serve_live.ps1" -ForegroundColor Green
    exit 0
}
Write-Host "RED - do NOT restart live. Fix failures first." -ForegroundColor Red
exit 1
