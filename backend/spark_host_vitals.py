"""Independent, read-only Windows system vitals for the SPARK cockpit.

Uses Windows public kernel32 telemetry interfaces from the Python standard
library. Does not import or redistribute source from external AI projects.
Does not request administration, list processes, access credentials, change
Windows settings, call cloud models, or install dependencies.

No telemetry is stored. Call only from an approved connected cockpit session.
"""
import math
import os
import shutil
import time

VITAL_FIELDS=("cpu_percent","ram_percent","ram_total_gb","ram_available_gb",
              "disk_total_gb","disk_free_gb","battery_percent","ac_connected")
EMPTY_VITALS={key:None for key in VITAL_FIELDS}

def _measure(value, *, max_value, decimals):
    if type(value) not in (float,int):
        return None
    number=float(value)
    if not math.isfinite(number) or number<0 or number>max_value:
        return None
    return round(number,decimals)

def normalize_host_vitals(raw):
    """Whitelist only bounded, scalar performance counters and power status."""
    if not isinstance(raw,dict):
        return dict(EMPTY_VITALS)
    out={
        "cpu_percent":_measure(raw.get("cpu_percent"), max_value=100,decimals=1),
        "ram_percent":_measure(raw.get("ram_percent"), max_value=100,decimals=1),
        "ram_total_gb":_measure(raw.get("ram_total_gb"),max_value=1048576,decimals=2),
        "ram_available_gb":_measure(raw.get("ram_available_gb"),max_value=1048576,decimals=2),
        "disk_total_gb":_measure(raw.get("disk_total_gb"),max_value=1048576,decimals=2),
        "disk_free_gb":_measure(raw.get("disk_free_gb"),max_value=1048576,decimals=2),
        "battery_percent":_measure(raw.get("battery_percent"),max_value=100,decimals=1),
        "ac_connected":raw.get("ac_connected") if type(raw.get("ac_connected")) is bool else None,
    }
    if out["ram_total_gb"] is not None and out["ram_available_gb"] is not None:
        if out["ram_available_gb"]>out["ram_total_gb"]:
            out["ram_available_gb"]=None
    if out["disk_total_gb"] is not None and out["disk_free_gb"] is not None:
        if out["disk_free_gb"]>out["disk_total_gb"]:
            out["disk_free_gb"]=None
    return out

def calculate_cpu_busy(before, after):
    """Return CPU percentage based on Win32 GetSystemTimes counters.

    kernel time includes idle, therefore CPU = 100*(1-idle/(kernel+user)).
    No third-party system monitoring libraries required.
    """
    try:
        idle0,kernel0,user0=before
        idle1,kernel1,user1=after
        elapsed_idle=idle1-idle0
        elapsed_total=(kernel1-kernel0)+(user1-user0)
        if elapsed_idle<0 or elapsed_total<=0 or elapsed_idle>elapsed_total:
            return None
        return round(100*(1-elapsed_idle/elapsed_total),1)
    except (TypeError,ValueError,ZeroDivisionError):
        return None

def _windows_vitals():
    import ctypes
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_=[("low",wintypes.DWORD),("high",wintypes.DWORD)]

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_=[
            ("dwLength",wintypes.DWORD),
            ("dwMemoryLoad",wintypes.DWORD),
            ("ullTotalPhys",ctypes.c_ulonglong),
            ("ullAvailPhys",ctypes.c_ulonglong),
            ("ullTotalPageFile",ctypes.c_ulonglong),
            ("ullAvailPageFile",ctypes.c_ulonglong),
            ("ullTotalVirtual",ctypes.c_ulonglong),
            ("ullAvailVirtual",ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual",ctypes.c_ulonglong),
        ]

    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_=[
            ("ACLineStatus",ctypes.c_byte),
            ("BatteryFlag",ctypes.c_ubyte),
            ("BatteryLifePercent",ctypes.c_ubyte),
            ("SystemStatusFlag",ctypes.c_ubyte),
            ("BatteryLifeTime",wintypes.DWORD),
            ("BatteryFullLifeTime",wintypes.DWORD),
        ]

    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    cpu=None
    def sample_times():
        idle,kernel_time,user=FILETIME(),FILETIME(),FILETIME()
        if not kernel.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kernel_time),ctypes.byref(user)):
            return None
        def ticks(ft):
            return (int(ft.high)<<32)|int(ft.low)
        return ticks(idle),ticks(kernel_time),ticks(user)

    before=sample_times()
    if before is not None:
        time.sleep(0.12)
        after=sample_times()
        if after is not None:
            cpu=calculate_cpu_busy(before,after)

    data=dict(EMPTY_VITALS)
    data["cpu_percent"]=cpu
    memory=MEMORYSTATUSEX()
    memory.dwLength=ctypes.sizeof(memory)
    if kernel.GlobalMemoryStatusEx(ctypes.byref(memory)) and memory.ullTotalPhys>0:
        gib=1024**3
        data["ram_percent"]=100*(1-memory.ullAvailPhys/memory.ullTotalPhys)
        data["ram_total_gb"]=memory.ullTotalPhys/gib
        data["ram_available_gb"]=memory.ullAvailPhys/gib

    power=SYSTEM_POWER_STATUS()
    if kernel.GetSystemPowerStatus(ctypes.byref(power)):
        if power.BatteryFlag!=128 and power.BatteryLifePercent!=255:
            data["battery_percent"]=float(power.BatteryLifePercent)
        if power.ACLineStatus in (0,1):
            data["ac_connected"]=(power.ACLineStatus==1)

    # Only the drive containing the current Windows Python installation is
    # inspected. No drive names, paths, serial numbers or volume IDs returned.
    root=os.path.splitdrive(os.path.abspath(os.sys.executable))[0]+"\\"
    if root!="\\":
        try:
            disk=shutil.disk_usage(root)
            data["disk_total_gb"]=disk.total/(1024**3)
            data["disk_free_gb"]=disk.free/(1024**3)
        except OSError:
            pass
    return data

def collect_host_vitals(*,sampler=None,platform_name=None):
    """Fail closed on unsupported machines without faking device readings."""
    target=os.name if platform_name is None else platform_name
    if sampler is None and target!="nt":
        return dict(EMPTY_VITALS)
    try:
        source=sampler() if sampler is not None else _windows_vitals()
        return normalize_host_vitals(source)
    except (OSError,RuntimeError,AttributeError,ValueError,TypeError):
        return dict(EMPTY_VITALS)
