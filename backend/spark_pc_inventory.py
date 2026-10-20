"""Read-only Windows management-agent inventories (master prompt section 5).

Startup entries come from the native registry API (stdlib `winreg`, HKCU and
HKLM in both registry views plus the Startup folders). The running-process list
comes from one bounded, fixed PowerShell `Get-Process` call with no
administration. Nothing here terminates, disables, deletes or writes anything;
closing recommendations are advisories the user must act on themselves.
"""
import json
import os
import subprocess
import time

try:
    import winreg
except ImportError:  # pragma: no cover - tests inject a fake registry
    winreg = None

_MAX_STARTUP = 128
_MAX_PROCESSES = 400
_PROCESS_TIMEOUT = 60

_RUN_SUBKEYS = (
    "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
    "Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
)

PROCESS_SOURCE = (
    "Get-Process | Select-Object Id,ProcessName,CPU,WorkingSet64,Responding | "
    "ConvertTo-Json -Compress -Depth 2"
)

PROTECTED_PROCESS_NAMES = (
    "csrss", "dwm", "lsass", "services", "smss", "svchost", "system",
    "wininit", "winlogon", "msmpeng", "mssense", "securityhealthservice",
    "explorer", "audiodg", "fontdrvhost", "registry", "idle",
    "memory compression", "conhost", "trustinstaller", "spoolsv",
)


class PcInventoryError(RuntimeError):
    pass


def _startup_submenu(registry, base, view, label, subkey, entries):
    try:
        key = registry.OpenKey(base, subkey, 0, view)
    except OSError:
        return
    with key:
        count = registry.QueryInfoKey(key)[0]
        for index in range(count):
            if len(entries) >= _MAX_STARTUP:
                return
            try:
                name, value, kind = registry.EnumValue(key, index)
            except OSError:
                continue
            if not isinstance(name, str) or not name.strip():
                continue
            entries.append({
                "name": name.strip(),
                "command": value.strip() if isinstance(value, str) else "",
                "source": f"{label}:{subkey.rsplit(chr(92), 1)[-1]}",
            })


def _startup_folder(folders_source, label, entries):
    if callable(folders_source):
        folders_source = folders_source()
    if not isinstance(folders_source, list):
        return
    for name in folders_source:
        if not isinstance(name, str) or not name.strip():
            continue
        if len(entries) >= _MAX_STARTUP:
            return
        entries.append({"name": name.strip(), "command": "", "source": label})


def startup_inventory(*, registry=None, user_startup=None, common_startup=None):
    """List startup entries, bounded, read-only, merge-safe against corrupt
    values. Each injector overrides a native source for testability; default
    uses the real registry and the current user's Startup folders."""
    entries = []
    if registry is None and winreg is None:
        return {"entries": [], "count": 0, "truncated": False,
                "note": "Registry enumeration is unavailable on this platform."}
    native = registry if registry is not None else winreg
    for base, label in (
        (native.HKEY_CURRENT_USER, "HKCU"),
        (native.HKEY_LOCAL_MACHINE, "HKLM"),
    ):
        views = [native.KEY_READ]
        wow32 = getattr(native, "KEY_WOW64_32KEY", 0)
        if wow32:
            views.append(native.KEY_READ | wow32)
        for view in views:
            for subkey in _RUN_SUBKEYS:
                _startup_submenu(native, base, view, label, subkey, entries)
    folders = []
    if user_startup is None:
        user_startup = _startup_folder_names(os.path.join(
            os.environ.get("APPDATA", ""), "Microsoft", "Windows",
            "Start Menu", "Programs", "Startup"))
    if common_startup is None:
        common_startup = _startup_folder_names(os.path.join(
            os.environ.get("PROGRAMDATA", ""), "Microsoft", "Windows",
            "Start Menu", "Programs", "Startup"))
    _startup_folder(user_startup, "user-startup-folder", entries)
    if common_startup:
        _startup_folder(common_startup, "common-startup-folder", entries)
    return {
        "entries": entries,
        "count": len(entries),
        "truncated": len(entries) >= _MAX_STARTUP,
        "note": ("Inventory only: nothing is started, stopped or removed. "
                 "Disable choices yourself or through an approved, confirmed action."),
    }


def _startup_folder_names(folder):
    try:
        return sorted(entry for entry in os.listdir(folder)
                      if entry.endswith(".lnk"))
    except OSError:
        return []


def _clean_processes(raw):
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("ProcessName")
        pid = item.get("Id")
        if not isinstance(name, str) or not name \
                or not isinstance(pid, int) or pid <= 0:
            continue
        ram = item.get("WorkingSet64")
        cpu = item.get("CPU")
        responding = item.get("Responding")
        out.append({
            "pid": pid,
            "name": name,
            "ram_mb": round(ram / 1048576, 1) if isinstance(ram, (int, float)) else None,
            "cpu_seconds": round(cpu, 1) if isinstance(cpu, (int, float)) else None,
            "responding": responding if isinstance(responding, bool) else None,
        })
        if len(out) >= _MAX_PROCESSES:
            break
    return out


def process_inventory(*, runner=None):
    """One fixed, bounded PowerShell `Get-Process` read. No elevation, no
    writes. `runner` injects the sample text for tests."""
    if runner is None:
        runner = _power_shell_runner
    try:
        text = runner(PROCESS_SOURCE)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PcInventoryError("Process inventory could not run.") from error
    try:
        raw = json.loads(text)
        if isinstance(raw, dict):
            raw = [raw]
    except (TypeError, ValueError):
        raise PcInventoryError("The PowerShell inventory returned unreadable data.") from None
    processes = _clean_processes(raw if isinstance(raw, list) else [])
    processes.sort(key=lambda item: item.get("ram_mb") or 0, reverse=True)
    return {
        "processes": processes,
        "count": len(processes),
        "truncated": False,
        "note": ("Read-only snapshot. Closing any process here happens only "
                 "through you; SPARK does not terminate anything."),
    }


def _power_shell_runner(command):
    root = os.environ.get("SystemRoot") or "C:/Windows"
    executable = os.path.join(root, "System32", "WindowsPowerShell", "v1.0",
                              "powershell.exe")
    if not os.path.isfile(executable):
        executable = "powershell"
    result = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", command],
        capture_output=True, timeout=_PROCESS_TIMEOUT, text=True,
        encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise PcInventoryError("The PowerShell inventory call failed.")
    return result.stdout


def advisory(vitals, startup, processes):
    """Pure PC-optimization advisory. Closing a process stays user-approved."""
    findings = []
    ram_percent = vitals.get("ram_percent") if isinstance(vitals, dict) else None
    if isinstance(ram_percent, (int, float)) and ram_percent >= 90:
        findings.append({
            "kind": "resource_pressure", "name": "ram",
            "evidence": f"RAM is at {ram_percent}%.",
            "recommendation": "Close the heaviest user applications you opened yourself.",
            "acted_automatically": False})
    disk_free = vitals.get("disk_free_gb") if isinstance(vitals, dict) else None
    if isinstance(disk_free, (int, float)) and disk_free < 10:
        findings.append({
            "kind": "resource_pressure", "name": "disk",
            "evidence": f"Only {disk_free} GB free.",
            "recommendation": "Clear temporary files through the PC scan screen, not manually here.",
            "acted_automatically": False})
    heavy = []
    if isinstance(processes, list):
        for item in processes:
            ram = item.get("ram_mb") if isinstance(item, dict) else None
            if isinstance(ram, (int, float)) and ram >= 250:
                heavy.append(item)
            if len(heavy) >= 5:
                break
    protected = 0
    for item in heavy:
        name = (item.get("name") or "").strip()
        key = name.casefold()
        safe = key not in PROTECTED_PROCESS_NAMES
        if not safe:
            protected += 1
        findings.append({
            "kind": "heavy_process", "pid": item.get("pid"), "name": name,
            "evidence": f"Using {item.get('ram_mb')} MB.",
            "recommendation": ("Protected by the SPARK safety list; leave it alone."
                               if not safe else
                               "Closable by you; confirm inside the owning application first."),
            "safe_to_close": safe,
            "acted_automatically": False})
    if isinstance(startup, list) and len(startup) > 12:
        findings.append({
            "kind": "startup_load", "name": "startup",
            "evidence": f"{len(startup)} startup entries.",
            "recommendation": "Review the startup inventory and disable entries you do not need.",
            "acted_automatically": False})
    return {
        "findings": findings,
        "protected_count": protected,
        "note": ("Advisory only. SPARK closes nothing and changes nothing; "
                 "every action here stays with you."),
    }
