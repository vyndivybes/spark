"""Local resource assessment and confirmed cleanup of old temporary files."""
import os
from pathlib import Path
import secrets
import stat
import tempfile
import threading
import time
from spark_host_vitals import collect_host_vitals

class PcOptimizer:
    def __init__(self, temp_root=None, sampler=None):
        self.root = Path(temp_root or tempfile.gettempdir()).absolute()
        self.sampler = sampler or collect_host_vitals
        self.lock = threading.Lock()
        self.plan = None

    @staticmethod
    def regular(info):
        return stat.S_ISREG(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 0x400)

    def check_root(self):
        for path in (self.root, *self.root.parents):
            if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('Linked temporary directories are not supported.')

    def scan(self):
        with self.lock:
            self.plan = None
            self.check_root()
            candidates = []
            examined = 0
            cutoff = time.time() - 7 * 86400
            with os.scandir(self.root) as entries:
                for entry in entries:
                    examined += 1
                    if examined > 5000:
                        break
                    if not entry.name.lower().endswith('.tmp'):
                        continue
                    try:
                        info = (self.root / entry.name).lstat()
                        if self.regular(info) and info.st_mtime < cutoff and info.st_size <= 100 * 1024**2:
                            candidates.append((entry.name, info))
                    except OSError:
                        continue
            token = secrets.token_hex(24)
            self.plan = (token, time.monotonic(), candidates)
            return {'host': self.sampler(), 'scan_id': token,
                    'files': [{'name': name, 'bytes': info.st_size} for name, info in candidates],
                    'eligible_bytes': sum(info.st_size for _, info in candidates),
                    'limited': examined > 5000,
                    'scope': 'Top-level .tmp files in your temporary folder, older than 7 days and at most 100 MB each. Folders are excluded.'}

    def cleanup(self, payload):
        if not isinstance(payload, dict) or payload.get('confirmed') is not True:
            raise ValueError('Confirm permanent deletion of the previewed files first.')
        with self.lock:
            plan = self.plan
            if not plan or payload.get('scan_id') != plan[0] or time.monotonic() - plan[1] > 600:
                raise ValueError('Preview expired or replaced. Scan again.')
            self.plan = None
            self.check_root()
            deleted = skipped = reclaimed = 0
            for name, before in plan[2]:
                path = self.root / name
                try:
                    current = path.lstat()
                    if not self.regular(current) or (current.st_ino, current.st_dev, current.st_size, current.st_mtime_ns) != (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns):
                        skipped += 1
                        continue
                    path.unlink()
                    deleted += 1
                    reclaimed += before.st_size
                except OSError:
                    skipped += 1
            return {'deleted': deleted, 'skipped': skipped, 'reclaimed_bytes': reclaimed}
