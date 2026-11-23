"""Project-scoped, explicit, evidence-attributed personal memory.

Does not ingest chats, email, clipboard, or files automatically.
All persistence is local, with bounded content and explicit deletion.
"""
import re
from contextlib import closing
import sqlite3
import threading
import time
import uuid
from pathlib import Path

_PROJECT = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_SECRET = re.compile(r"(?i)(?:api[_ -]?key|password|bearer|client[_ -]?secret|private[_ -]?key|access[_ -]?token)\s*[:=]")
_SOURCES = frozenset({"user_explicit", "verified_document", "observed_result"})

class MemoryError(ValueError):
    pass

class PersonalMemory:
    def __init__(self, root, clock=None):
        self.root = Path(root) / "personal-memory"
        self.clock = clock or time.time
        self.lock = threading.RLock()

    def _database(self, project):
        if not isinstance(project, str) or not _PROJECT.fullmatch(project) or len(project)>64:
            raise MemoryError("Invalid project.")
        if self.root.is_symlink():
            raise MemoryError("Linked memory folder forbidden.")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / (project + ".sqlite3")
        if path.is_symlink():
            raise MemoryError("Linked memory database forbidden.")
        db = sqlite3.connect(path, timeout=5)
        db.execute("CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, body TEXT NOT NULL, source TEXT NOT NULL, confidence REAL NOT NULL, created REAL NOT NULL, expiry REAL NOT NULL)")
        return db

    def remember(self, project, body, *, source="user_explicit", confidence=1.0, ttl_days=30):
        if not isinstance(body,str) or not 1 <= len(body.strip()) <= 512 or "\x00" in body:
            raise MemoryError("Memory text must be 1–512 characters.")
        if _SECRET.search(body):
            raise MemoryError("Credential-shaped text cannot be stored.")
        if source not in _SOURCES or type(confidence) not in (float,int) or not 0 <= confidence <= 1:
            raise MemoryError("Unsupported provenance or confidence.")
        if type(ttl_days) is not int or not 1 <= ttl_days <= 365:
            raise MemoryError("TTL must be 1–365 days.")
        now = self.clock()
        identity=uuid.uuid4().hex
        with self.lock, closing(self._database(project)) as db, db:
            db.execute("INSERT INTO memories VALUES (?,?,?,?,?,?)",
                       (identity,body.strip(),source,float(confidence),now,now+ttl_days*86400))
        return {"id":identity,"source":source,"expires_at":now+ttl_days*86400}

    def list(self, project):
        with self.lock, closing(self._database(project)) as db, db:
            db.execute("DELETE FROM memories WHERE expiry <= ?",(self.clock(),))
            rows=db.execute("SELECT id,body,source,confidence,created,expiry FROM memories ORDER BY created DESC, id DESC LIMIT 100").fetchall()
        return [{"id":i,"body":body,"source":source,"confidence":confidence,
                 "created_at":created,"expires_at":expires} for i,body,source,confidence,created,expires in rows]

    def forget(self, project, identity):
        if not isinstance(identity,str) or not re.fullmatch(r"[a-f0-9]{32}",identity):
            raise MemoryError("Invalid memory identifier.")
        with self.lock, closing(self._database(project)) as db, db:
            deleted=db.execute("DELETE FROM memories WHERE id=?",(identity,)).rowcount
        return {"deleted":bool(deleted)}
