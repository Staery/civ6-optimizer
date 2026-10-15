# PROMOTE to LIVE: restart the production server on port 8000.
# Run scripts\check.ps1 first - only promote when it is GREEN.
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = "utf-8"

# stop only the process listening on 8000 (leaves the 8001 dev server alone)
$c = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($c) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 400 }

Start-Process -NoNewWindow python -ArgumentList "-m","uvicorn","backend.app:app","--host","127.0.0.1","--port","8000"
Start-Sleep -Seconds 3
try {
    $code = (Invoke-WebRequest http://127.0.0.1:8000/ -UseBasicParsing).StatusCode
    Write-Host "LIVE up on http://127.0.0.1:8000 (HTTP $code)" -ForegroundColor Green
} catch {
    Write-Host "LIVE not responding yet - check the uvicorn output." -ForegroundColor Red
}
