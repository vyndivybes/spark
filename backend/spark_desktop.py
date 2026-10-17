"""Constrained Windows desktop application launcher.

No shell, arbitrary paths, arguments, or user-supplied executables.
Permission must be separately granted by the SPARK confirmation flow.
"""
import os
import subprocess
import sys

ALLOWED_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
}


def launch_allowed_app(name, *, platform=None, starter=None):
    platform = sys.platform if platform is None else platform
    if platform != "win32":
        return {"ok": False, "message": "Desktop application launching requires Windows."}
    if not isinstance(name, str) or name not in ALLOWED_APPS:
        return {"ok": False, "message": "Application not on the approved launch list."}
    if starter is None:
        starter = subprocess.Popen
    try:
        starter([ALLOWED_APPS[name]], shell=False, close_fds=True,
                cwd=os.environ.get("SYSTEMROOT", "C:\\Windows"))
    except OSError:
        return {"ok": False, "message": "Windows could not start the approved application."}
    return {"ok": True, "message": f"Started {name}."}
