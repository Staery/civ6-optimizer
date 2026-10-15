@echo off
setlocal
cd /d "%~dp0"
title Civ6 District Optimizer

REM --- if the server is already running, just open the browser and exit ---
powershell -NoProfile -Command "try{ Invoke-WebRequest http://127.0.0.1:8000/api/meta -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel%==0 (
  echo Server already running. Opening browser...
  start "" http://127.0.0.1:8000
  goto :eof
)

REM --- check Python ---
where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python not found in PATH. Install Python 3.11+ and try again.
  pause
  goto :eof
)

REM --- install dependencies on first run ---
python -c "import fastapi, uvicorn" 1>nul 2>nul
if errorlevel 1 (
  echo Installing dependencies ^(first run, one time^)...
  python -m pip install -e .
  if errorlevel 1 (
    echo [!] Dependency install failed.
    pause
    goto :eof
  )
)

REM --- open the browser shortly after, then run the server in this window ---
echo Starting server at http://127.0.0.1:8000  (close this window or press Ctrl+C to stop)
start "" cmd /c "ping -n 3 127.0.0.1 >nul & start "" http://127.0.0.1:8000"
python -m uvicorn backend.app:app --app-dir "%~dp0" --host 127.0.0.1 --port 8000

endlocal
