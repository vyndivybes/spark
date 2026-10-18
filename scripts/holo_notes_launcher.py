"""Launch the original MIT-licensed HOLO server over a user-approved notes vault.

Loads the original vendor source unchanged. No extra services, remote API,
shell launcher, or background camera. The browser still explicitly owns the webcam.
"""
import importlib.util
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
UPSTREAM=ROOT/"vendor"/"holo-gestures"/"server.py"
SAMPLE=ROOT/"vendor"/"holo-gestures"/"sample-notes"


def choose_notes_dir(configured,fallback=SAMPLE):
    source=Path(configured).expanduser() if configured else None
    if source and source.is_dir() and not source.is_symlink():
        return source.resolve()
    return Path(fallback)


def load_vendor(server_path,notes_dir):
    """Execute only HOLO's unchanged server module, substituting note source."""
    source=Path(server_path).resolve()
    if source.name!="server.py" or not source.is_file():
        raise ValueError("HOLO source is unavailable.")
    folder=Path(notes_dir).resolve()
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError("An existing, real notes folder is required.")
    spec=importlib.util.spec_from_file_location("spark_holo_original_server",source)
    if not spec or not spec.loader:
        raise ValueError("Could not read the installed HOLO server.")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.notes_dir=lambda: str(folder)
    return module


def main():
    notes=choose_notes_dir(os.environ.get("SPARK_HOLO_NOTES_DIR"),SAMPLE)
    holo=load_vendor(UPSTREAM,notes)
    print(f"SPARK HOLO original gesture engine on 127.0.0.1:{holo.PORT}",flush=True)
    holo.ThreadingHTTPServer(("127.0.0.1",holo.PORT),holo.H).serve_forever()


if __name__=="__main__":
    main()
