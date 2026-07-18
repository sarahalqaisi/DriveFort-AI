@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo [DriveFort AI] Windows launcher

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python and enable Add Python to PATH.
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

python -m pip install --upgrade pip
pip install -r requirements.txt

set DRIVEFORT_DEBUG=0
set DRIVEFORT_HOST=127.0.0.1
set DRIVEFORT_PORT=5000

echo Opening http://127.0.0.1:5000
start http://127.0.0.1:5000
python app.py
pause
