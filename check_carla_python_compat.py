from __future__ import annotations

import platform
import sys
from src.carla_runtime import (
    REQUIRED_CARLA_VERSION,
    REQUIRED_PYTHON_DISPLAY,
    current_python_is_64bit,
    current_python_is_supported,
    ensure_carla_on_path,
    expected_egg_hint,
    find_matching_carla_package,
)

print("ZoneGuard CARLA/Python compatibility check")
print("Required Python:", REQUIRED_PYTHON_DISPLAY, "or any Python 3.7.x 64-bit")
print("Required CARLA:", REQUIRED_CARLA_VERSION)
print("Current Python:", sys.version.replace("\n", " "))
print("Platform:", platform.platform())
print("Architecture:", platform.architecture()[0])

if not current_python_is_supported():
    print("Python check: FAILED")
    print("Use Python 3.7 with: py -3.7 check_carla_python_compat.py")
    raise SystemExit(1)
if not current_python_is_64bit():
    print("Python check: FAILED")
    print("Your Python 3.7 is 32-bit. Install Python 3.7 Windows x86-64 executable installer.")
    raise SystemExit(1)

print("Python check: OK")
ok, message = ensure_carla_on_path()
print("CARLA API:", message)

if ok:
    try:
        import carla  # type: ignore
        print("Import test: OK")
        print("CARLA module:", getattr(carla, "__file__", "built-in/unknown"))
    except Exception as exc:
        print("Import test: FAILED")
        print("Reason:", exc)
        raise SystemExit(2)
else:
    _, discovered = find_matching_carla_package()
    if discovered:
        print("Discovered CARLA packages:")
        for pkg in discovered:
            print(" -", pkg)
    else:
        print("Expected wheel example:", expected_egg_hint())
    raise SystemExit(1)
