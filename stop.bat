@echo off
setlocal
cd /d "%~dp0"
title Civ6 District Optimizer - stop

echo Stopping Civ6 Optimizer server on port 8000...
powershell -NoProfile -Command ^
  "$c = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; if($c){ $c.OwningProcess | Sort-Object -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force; Write-Host ('  stopped PID ' + $_) } catch {} } } else { Write-Host '  no server was running on port 8000.' }"

echo Done.
timeout /t 2 >nul
endlocal
