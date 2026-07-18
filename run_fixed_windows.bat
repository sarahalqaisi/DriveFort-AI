@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo [DriveFort AI] Fixed launcher - ensures the diagnostics route is loaded.
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
  echo Stopping old process on port 5000: %%a
  taskkill /PID %%a /F >nul 2>nul
)
where python >nul 2>nul || (echo Python not found.& pause & exit /b 1)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python verify_routes.py
if errorlevel 1 (
  echo Route verification failed.
  pause
  exit /b 1
)
set DRIVEFORT_DEBUG=0
set DRIVEFORT_HOST=127.0.0.1
set DRIVEFORT_PORT=5000
start "" http://127.0.0.1:5000
python app.py
pause
