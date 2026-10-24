"""Resumable, read-only name/path search over the owner's accessible local drives."""
import ctypes
import fnmatch
import json
import os
from pathlib import Path
import re
import secrets
import time


def local_roots():
    if os.name != 'nt':
        return ['/']
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    return [f'{chr(65 + index)}:\\' for index in range(26)
            if mask & (1 << index) and ctypes.windll.kernel32.GetDriveTypeW(f'{chr(65 + index)}:\\') in (2, 3)]


class FileSearch:
    def __init__(self, root, *, entry_budget=4000, time_budget=2):
        self.root = Path(root)
        self.entry_budget = entry_budget
        self.time_budget = time_budget

    def search(self, query, *, path=None, limit=50, cursor=None):
        if (not isinstance(query, str) or not query.strip() or len(query) > 200
                or any(ord(c) < 32 for c in query)
                or type(limit) is not int or not 1 <= limit <= 100):
            raise ValueError('Use a file-name/path query of 1–200 characters and limit 1–100.')
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise ValueError('Linked search storage is not allowed.')
        if cursor is not None and (not isinstance(cursor, str) or not re.fullmatch(r'[0-9a-f]{32}', cursor)):
            raise ValueError('Use only a returned search cursor.')
        identity = cursor or secrets.token_hex(16)
        storage = self.root / (identity + '.json')
        if storage.is_symlink():
            raise ValueError('Linked search cursors are not allowed.')
        if cursor:
            if not storage.is_file() or storage.stat().st_size > 2_000_000:
                raise ValueError('Search cursor is unavailable; start a new search.')
            state = json.loads(storage.read_text(encoding='utf-8'))
            if state['expires'] < time.time() or state['query'] != query.strip() or state['requested_path'] != path:
                raise ValueError('Search cursor expired or belongs to a different query/scope.')
        else:
            roots = [str(Path(path).expanduser().resolve())] if path is not None else local_roots()
            if path is not None and not Path(roots[0]).is_dir():
                raise ValueError('Search path must be an accessible directory.')
            state = {'query': query.strip(), 'requested_path': path, 'roots': roots,
                     'pending': list(reversed(roots)), 'current': None, 'offset': 0,
                     'scanned': 0, 'skipped_directories': 0, 'skipped_links': 0,
                     'expires': time.time() + 86400}
        needle = state['query'].casefold()
        glob = any(c in needle for c in '*?[')
        results, consumed = [], 0
        deadline = time.monotonic() + self.time_budget
        while state['current'] is not None or state['pending']:
            if state['current'] is None:
                state['current'] = state['pending'].pop()
                state['offset'] = 0
            directory = state['current']
            paused = False
            try:
                with os.scandir(directory) as entries:
                    for index, entry in enumerate(entries):
                        if index < state['offset']:
                            continue
                        state['offset'] = index + 1
                        state['scanned'] += 1
                        consumed += 1
                        try:
                            info = entry.stat(follow_symlinks=False)
                            linked = entry.is_symlink() or bool(getattr(info, 'st_file_attributes', 0) & 0x400)
                            is_directory = entry.is_dir(follow_symlinks=False)
                            if linked:
                                state['skipped_links'] += 1
                            elif is_directory:
                                state['pending'].append(entry.path)
                            matches = (fnmatch.fnmatchcase(entry.name.casefold(), needle) if glob
                                       else needle in entry.name.casefold() or needle in entry.path.casefold())
                            if matches:
                                results.append({'name': entry.name, 'path': entry.path, 'directory': is_directory})
                        except OSError:
                            state['skipped_directories'] += 1
                        if len(results) >= limit or consumed >= self.entry_budget or time.monotonic() >= deadline:
                            paused = True
                            break
            except OSError:
                state['skipped_directories'] += 1
            if paused:
                break
            state['current'], state['offset'] = None, 0
        finished = state['current'] is None and not state['pending']
        if finished:
            storage.unlink(missing_ok=True)
        else:
            payload = json.dumps(state)
            if len(payload.encode()) > 2_000_000:
                raise ValueError('Search state reached its bound. Search individual drives or folders.')
            pending = storage.with_suffix('.pending')
            pending.write_text(payload, encoding='utf-8')
            os.replace(pending, storage)
        return {'ok': True, 'read_only': True, 'query': state['query'], 'roots': state['roots'],
                'matches': results, 'shown': len(results), 'scanned_entries': state['scanned'],
                'next_cursor': None if finished else identity, 'enumeration_finished': finished,
                'coverage_complete': finished and not state['skipped_directories'] and not state['skipped_links'],
                'skipped_directories': state['skipped_directories'], 'skipped_links': state['skipped_links'],
                'scope': 'File and folder names/paths on accessible local drives; no file contents are read. Network and offline drives are excluded.',
                'limitation': 'Continue with the same query, path and next_cursor until enumeration_finished. A partial scan is not proof of absence. Permission-denied and linked locations are skipped. The live filesystem can change between pages.'}
