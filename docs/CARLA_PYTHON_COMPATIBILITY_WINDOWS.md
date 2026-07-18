# CARLA 0.9.13 + Python 3.8.10 setup for Windows

This project has been configured for your local versions:

- Python: **3.8.10** / any Python **3.8.x** interpreter
- CARLA: **0.9.13**
- Expected CARLA Python API egg: `carla-0.9.13-py3.8-win-amd64.egg`

## Recommended launch

Run:

```bat
run_carla_windows.bat
```

The launcher uses `py -3.8`, creates `.venv38`, installs Python-3.8-compatible packages, and checks that the CARLA 0.9.13 Python API egg can be imported.

## CARLA path

If CARLA is not detected automatically, set `CARLA_ROOT` before running the launcher. Example:

```bat
set CARLA_ROOT=C:\CARLA_0.9.13\WindowsNoEditor
run_carla_windows.bat
```

You can also set the exact egg path:

```bat
set CARLA_EGG_PATH=C:\CARLA_0.9.13\WindowsNoEditor\PythonAPI\carla\dist\carla-0.9.13-py3.8-win-amd64.egg
run_carla_windows.bat
```

## Manual compatibility check

```bat
py -3.8 check_carla_python_compat.py
```

Expected successful result:

```text
Python check: OK
CARLA API: Using CARLA 0.9.13 Python 3.8 API: ...carla-0.9.13-py3.8-win-amd64.egg
Import test: OK
```

If the CARLA egg is missing or mismatched, the dashboard still opens in safe Mock mode, but live CARLA connection will not be available until the exact egg is found.
