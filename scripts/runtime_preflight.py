"""Offline SPARK backend dependency check; never reads credentials or starts hardware."""
import importlib.util
import sys

REQUIRED = {
    "python-socketio": "socketio",
    "uvicorn": "uvicorn",
    "fastapi": "fastapi",
    "google-genai": "google.genai",
    "opencv-python": "cv2",
    "pyaudio": "pyaudio",
    "pillow": "PIL",
    "mss": "mss",
    "python-dotenv": "dotenv",
    "python-kasa": "kasa",
    "mediapipe": "mediapipe",
    "numpy": "numpy",
    "aiohttp": "aiohttp",
    "zeroconf": "zeroconf",
    "playwright": "playwright",
}


def missing_dependencies(find_spec=None):
    probe = find_spec or importlib.util.find_spec
    missing = []
    for package, module in REQUIRED.items():
        try:
            if probe(module) is None:
                missing.append(package)
        except (ImportError, ModuleNotFoundError, ValueError):
            missing.append(package)
    return missing


def main():
    if not (sys.version_info.major == 3 and (3, 11) <= sys.version_info[:2] <= (3, 13)):
        print("SPARK runtime: Python 3.11-3.13 required for this build; Python 3.12 recommended.")
        return 2
    missing = missing_dependencies()
    if missing:
        print("SPARK runtime missing packages: " + ", ".join(missing))
        print("Install in a dedicated venv: python -m pip install -r requirements-runtime.txt")
        return 2
    print("SPARK runtime module preflight: PASS (no hardware/provider checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
