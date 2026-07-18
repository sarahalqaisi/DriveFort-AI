@echo off
set "CARLA_EXE_PATH=D:\Downloads\CarlaSimulator\WindowsNoEditor\CarlaUE4.exe"
setlocal EnableExtensions
cd /d "%~dp0"
echo [DriveFort AI] Starting CARLA 0.9.13 + Python 3.7.9 mode...

where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher ^(py^) was not found. Install Python 3.7 64-bit and enable Add Python to PATH.
  pause
  exit /b 1
)

py -3.7 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,7) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.7 64-bit was not found by the Python Launcher.
  echo Confirm this works: py -3.7 -c "import platform; print(platform.architecture())"
  pause
  exit /b 1
)

if not exist .venv37 (
  echo Creating virtual environment with Python 3.7 64-bit...
  py -3.7 -m venv --system-site-packages .venv37
)
call .venv37\Scripts\activate.bat

python -m pip install --upgrade "pip<25"
pip install -r requirements.txt

if exist "D:\Downloads\CarlaSimulator\WindowsNoEditor\PythonAPI\carla\dist\carla-0.9.13-cp37-cp37m-win_amd64.whl" (
  echo Installing CARLA 0.9.13 wheel into this environment...
  pip install "D:\Downloads\CarlaSimulator\WindowsNoEditor\PythonAPI\carla\dist\carla-0.9.13-cp37-cp37m-win_amd64.whl"
)

echo.
echo [DriveFort AI] Checking CARLA 0.9.13 / Python 3.7 compatibility...
python check_carla_python_compat.py
if errorlevel 1 (
  echo.
  echo [DriveFort AI] CARLA 0.9.13 Python API was not matched yet.
  echo If needed, install it manually:
  echo   py -3.7 -m pip install "D:\Downloads\CarlaSimulator\WindowsNoEditor\PythonAPI\carla\dist\carla-0.9.13-cp37-cp37m-win_amd64.whl"
  echo The web app may still run in safe Mock mode.
  echo.
)

set DRIVEFORT_HOST=127.0.0.1
set DRIVEFORT_PORT=5000
set ZONEGUARD_CARLA_HOST=localhost
set ZONEGUARD_CARLA_PORT=2000
set DRIVEFORT_DEBUG=0

echo Opening http://127.0.0.1:5000
start http://127.0.0.1:5000
python app.py
pause
