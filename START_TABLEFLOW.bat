@echo off
REM ===================================================================
REM  TableFlow Enterprise - one-click local demo for Windows
REM  Needs only Python 3.10+ (Anaconda is fine). Uses SQLite + the
REM  pre-built React UI, all served on http://localhost:8000
REM  First run: creates .venv, installs packages, seeds 60 days of data.
REM  Stop the app: close this window (or press Ctrl+C).
REM ===================================================================
setlocal
cd /d "%~dp0backend"
title TableFlow Enterprise
REM Virtual environment lives outside OneDrive so thousands of package files are not synced.
set "VENV=%LOCALAPPDATA%\TableFlow\venv"

set "PY="
if exist "%USERPROFILE%\anaconda3\python.exe" set "PY=%USERPROFILE%\anaconda3\python.exe"
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo [X] Python was not found. Install Python 3.12 from https://www.python.org/downloads/ and run this file again.
  pause & exit /b 1
)
echo [1/4] Using Python: %PY%
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" || (
  echo [X] Python 3.10 or newer is required. & %PY% --version & pause & exit /b 1
)

if not exist "%VENV%\Scripts\python.exe" (
  echo [2/4] Creating virtual environment ...
  %PY% -m venv "%VENV%" || (echo [X] Could not create virtual environment & pause & exit /b 1)
)
echo [2/4] Installing / checking packages (first run takes a few minutes) ...
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || (
  echo [X] Package install failed - check your internet connection. & pause & exit /b 1
)

set "DATABASE_URL=sqlite:///./tableflow_demo.db"
set "FRONTEND_DIST=%~dp0frontend\dist"
set "ENVIRONMENT=development"
set "LOG_LEVEL=WARNING"

if not exist "tableflow_demo.db" (
  echo [3/4] Creating database and loading 60 days of demo data ...
  "%VENV%\Scripts\python.exe" -m app.seed --create-schema --days 60 || (echo [X] Seeding failed & pause & exit /b 1)
) else (
  echo [3/4] Demo database already exists - delete backend\tableflow_demo.db to reset it.
)

echo [4/4] Starting TableFlow on http://localhost:8000  (API docs: http://localhost:8000/docs)
echo       Login: admin@tableflow.local  /  TableFlow!2026
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
"%VENV%\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
