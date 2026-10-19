"""Bounded local session/task memory with FTS5 and citation-preserving RRF.

RRF follows the ranking method inspected in OpenJarvis's Apache-2.0
tools/storage/hybrid.py at 2817faa5. This implementation uses SPARK record IDs.
"""
import hashlib
import json
import math
import re
import sqlite3
import time
from pathlib import Path


def reciprocal_rank_fusion(ranked_lists, k=60):
    if type(k) is not int or k < 1:
        raise ValueError('Invalid fusion constant')
    records, scores = {}, {}
    for ranked in ranked_lists:
        seen = set()
        for rank, record in enumerate(ranked):
            identifier = record['id']
            if identifier in seen:
                continue
            seen.add(identifier)
            records.setdefault(identifier, record)
            scores[identifier] = scores.get(identifier, 0) + 1 / (k + rank + 1)
    return [{**records[key], 'score': scores[key]} for key in sorted(scores, key=lambda key: (-scores[key], key))]


class Memory:
    def __init__(self, directory, *, clock=time.time):
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or (path/'memory.sqlite3').is_symlink():
            raise ValueError('Linked memory storage is prohibited')
        self.db = sqlite3.connect(path/'memory.sqlite3')
        self.db.execute('CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,project TEXT,kind TEXT,body TEXT,source TEXT,created REAL,expires REAL)')
        self.db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED,body)')
        self.clock = clock

    def _project(self, project):
        if not isinstance(project, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', project) or len(project)>60:
            raise ValueError('Invalid memory project')

    def remember(self, project, kind, body, source, *, ttl=2592000):
        self._project(project)
        if kind not in ('session', 'task', 'observation'):
            raise ValueError('Unsupported memory kind')
        if not isinstance(body, str) or not 1<=len(body.strip())<=10000 or not isinstance(source,str) or not 1<=len(source)<=300:
            raise ValueError('Bounded content and provenance are required')
        if type(ttl) not in (int,float) or not math.isfinite(ttl) or not 1<=ttl<=31536000:
            raise ValueError('Memory expiration must be between one second and one year')
        body=body.strip()
        identifier=hashlib.sha256(json.dumps([project,kind,body,source]).encode()).hexdigest()[:32]
        with self.db:
            self.db.execute('DELETE FROM memory_fts WHERE id IN (SELECT id FROM memories WHERE expires<=?)',(self.clock(),))
            self.db.execute('DELETE FROM memories WHERE expires<=?',(self.clock(),))
            exists=self.db.execute('SELECT id FROM memories WHERE id=?',(identifier,)).fetchone()
            if not exists:
                if self.db.execute('SELECT count(*) FROM memories WHERE project=?',(project,)).fetchone()[0]>=1000:
                    raise ValueError('Project memory limit reached; delete old records')
                self.db.execute('INSERT INTO memories VALUES (?,?,?,?,?,?,?)',(identifier,project,kind,body,source,self.clock(),self.clock()+ttl))
                self.db.execute('INSERT INTO memory_fts VALUES (?,?)',(identifier,body))
        return {'id':identifier,'source':source,'deduplicated':bool(exists)}

    def search(self, project, query, *, semantic=False):
        self._project(project)
        if not isinstance(query,str) or not 1<=len(query)<=500:
            raise ValueError('Search query must contain 1–500 characters')
        words=re.findall(r'\w+',query)[:20]
        if not words:
            return {'mode':'fts5','results':[],'semantic_available':False}
        expression=' OR '.join('"'+word+'"' for word in words)
        rows=self.db.execute('SELECT m.id,m.kind,m.body,m.source,m.created,m.expires,bm25(memory_fts) FROM memory_fts JOIN memories m ON memory_fts.id=m.id WHERE memory_fts MATCH ? AND m.project=? AND m.expires>? ORDER BY bm25(memory_fts) LIMIT 20',(expression,project,self.clock())).fetchall()
        results=[dict(zip(('id','kind','body','source','created','expires','bm25'),row)) for row in rows]
        return {'mode':'fts5','semantic_available':False,'fallback_reason':'No local embedding index configured' if semantic else None,'results':results}

    def delete(self, project, identifier):
        self._project(project)
        with self.db:
            row=self.db.execute('SELECT id FROM memories WHERE id=? AND project=?',(identifier,project)).fetchone()
            if not row:
                raise ValueError('Memory not found in this project')
            self.db.execute('DELETE FROM memory_fts WHERE id=?',(identifier,))
            self.db.execute('DELETE FROM memories WHERE id=? AND project=?',(identifier,project))
        return {'deleted':identifier}

    def close(self):
        self.db.close()
