# ZoneGuard ready setup: Python 3.7.9 + CARLA 0.9.13

هذه النسخة معدلة لتعمل مع بيئتك الحالية:

- Python 3.7.9 64-bit
- CARLA 0.9.13
- Wheel: `carla-0.9.13-cp37-cp37m-win_amd64.whl`
- المسار المتوقع عندك:
  `D:\Downloads\CarlaSimulator\WindowsNoEditor\PythonAPI\carla\dist\carla-0.9.13-cp37-cp37m-win_amd64.whl`

## التشغيل

1. شغلي CARLA أولًا:

```bat
D:\Downloads\CarlaSimulator\WindowsNoEditor\CarlaUE4.exe
```

2. من مجلد المشروع شغلي:

```bat
py -3.7 check_carla_python_compat.py
```

3. ثم:

```bat
run_carla_windows.bat
```

أو مباشرة:

```bat
py -3.7 app.py
```
