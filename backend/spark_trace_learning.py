"""Local workflow discovery using the pinned OpenJarvis learning component.

Stores tool names and execution outcomes only, never arguments or results.
Successful execution is not a user satisfaction or semantic correctness score.
"""
import json
import re
import threading
from dataclasses import asdict
from pathlib import Path

from spark_maintenance import atomic_write
from vendor.openjarvis_learning.skill_discovery import SkillDiscovery


class TraceLearning:
    def __init__(self, data_dir):
        self.root = Path(data_dir).resolve() / 'trace-learning'
        self.lock = threading.RLock()

    def _file(self, project):
        if not isinstance(project, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', project):
            raise ValueError('Invalid learning project.')
        path = self.root / (project + '.json')
        if self.root.is_symlink() or path.is_symlink():
            raise ValueError('Linked learning storage prohibited.')
        return path

    def _read(self, project):
        path = self._file(project)
        if not path.exists():
            return []
        if path.stat().st_size > 1_000_000:
            raise ValueError('Learning history exceeds its limit.')
        rows = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(rows, list) or len(rows) > 500:
            raise ValueError('Invalid learning history.')
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {'steps', 'outcome'}
                    or row['outcome'] not in ('success', 'failure')
                    or not isinstance(row['steps'], list) or not 1 <= len(row['steps']) <= 4
                    or any(not isinstance(s, dict) or set(s) != {'step_type', 'tool_name'}
                           or s['step_type'] != 'tool_call'
                           or not isinstance(s['tool_name'], str)
                           or not re.fullmatch(r'[a-zA-Z0-9_]{1,120}', s['tool_name'])
                           for s in row['steps'])):
                raise ValueError('Invalid learning trace.')
        return rows

    def record(self, project, names, succeeded):
        if not names or len(names) > 4 or any(
                not isinstance(n, str) or not re.fullmatch(r'[a-zA-Z0-9_]{1,120}', n) for n in names):
            raise ValueError('Invalid tool sequence.')
        with self.lock:
            rows = self._read(project)
            rows.append({'steps': [{'step_type': 'tool_call', 'tool_name': n} for n in names],
                         'outcome': 'success' if succeeded else 'failure'})
            atomic_write(self._file(project), json.dumps(rows[-500:]).encode())

    def patterns(self, project):
        with self.lock:
            # Each trace contributes at most one occurrence of each sequence;
            # require three separate observations, never a repeated single trace.
            found = SkillDiscovery(min_frequency=3, min_sequence_length=2,
                                   max_sequence_length=2, min_outcome=0.8)
            return [dict(asdict(s), advisory=True,
                         outcome_basis='execution success, not user-rated correctness')
                    for s in found.analyze_traces(self._read(project))][:20]
