# Actual source port from user-owned vyndivybes/ARKUS/knowledge_base.py
# Preserves ARKUS's validation, indexing and skill lifecycle behavior.
"""Private, project-isolated, dependency-free SQLite FTS5 knowledge base.

Only user-selected files are indexed. Sources are never sent to a provider
without a separate, configured model invocation.
"""
import hashlib
import io
import re
import secrets
import sqlite3
import threading
import zipfile
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime,timezone
from xml.etree import ElementTree

MAX_FILE=2_000_000
MAX_TEXT=400_000
MAX_DOCS=50
PROJECT=re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
FILE=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.() -]{0,119}\.(?:txt|md|markdown|docx|pdf)",re.I)
W_NS="{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

class KnowledgeError(ValueError):pass

def extract(name,raw):
    if not isinstance(raw,bytes) or not (0<len(raw)<=MAX_FILE):
        raise KnowledgeError("Choose a nonempty document of at most 2 MB.")
    if not isinstance(name,str) or not FILE.fullmatch(name) or ".." in name:
        raise KnowledgeError("Import a safe TXT, MD, DOCX or text PDF filename.")
    lower=name.lower()
    if lower.endswith((".txt",".md",".markdown")):
        try:text=raw.decode("utf-8-sig")
        except UnicodeDecodeError:raise KnowledgeError("Text documents must be UTF-8.") from None
    elif lower.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if len(z.infolist())>90 or sum(i.file_size for i in z.infolist())>4_000_000:
                    raise KnowledgeError("DOCX archive exceeds safe size limits.")
                meta=z.getinfo("word/document.xml")
                if meta.file_size>MAX_FILE:raise KnowledgeError("DOCX text is too large.")
                tree=ElementTree.fromstring(z.read(meta))
            paragraphs=[]
            for paragraph in tree.iter(W_NS+"p"):
                paragraphs.append("".join(t.text or "" for t in paragraph.iter(W_NS+"t")))
            text="\n".join(paragraphs)
        except (KeyError,zipfile.BadZipFile,ElementTree.ParseError,OSError) as e:
            raise KnowledgeError("Unreadable or unsupported DOCX.") from None
    else:
        if not raw.startswith(b"%PDF-"):raise KnowledgeError("Invalid PDF file.")
        try:
            from pypdf import PdfReader
        except ImportError:
            raise KnowledgeError("PDF text extraction requires optional pypdf; TXT, MD and DOCX are available offline.") from None
        try:
            reader=PdfReader(io.BytesIO(raw),strict=True)
            if reader.is_encrypted or len(reader.pages)>70:
                raise KnowledgeError("Encrypted or overlong PDF not supported.")
            text="\n".join(page.extract_text() or "" for page in reader.pages)
        except KnowledgeError:raise
        except Exception:
            raise KnowledgeError("Unreadable PDF or no extractable text. Scanned PDFs require OCR.") from None
    text=text.replace("\x00","").strip()
    if not text or len(text)>MAX_TEXT:
        raise KnowledgeError("Document has no extractable text or exceeds 400,000 characters.")
    return text

def chunks(text,size=850,overlap=100):
    parts=[];start=0
    while start<len(text):
        end=min(len(text),start+size)
        if end<len(text):
            split=max(text.rfind("\n",start+size//2,end),text.rfind(" ",start+size//2,end))
            if split>start+size//2:end=split
        part=text[start:end].strip()
        if part:parts.append(part)
        if end>=len(text):break
        start=max(start+1,end-overlap)
        if len(parts)>650:raise KnowledgeError("Too many document chunks.")
    return parts

class KnowledgeBase:
    def __init__(self,data_dir):
        self.root=Path(data_dir).resolve()/"knowledge"
        self.lock=threading.RLock()
    def _path(self,project):
        if not isinstance(project,str) or not PROJECT.fullmatch(project):
            raise KnowledgeError("Invalid project identifier.")
        path=self.root/project/"sources.sqlite3"
        if any(p.is_symlink() for p in (self.root,path.parent,path)):
            raise KnowledgeError("Linked knowledge directories are not permitted.")
        return path
    @contextmanager
    def _db(self,project):
        path=self._path(project);path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(str(path),timeout=5)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,name TEXT NOT NULL,sha TEXT NOT NULL,uploaded TEXT NOT NULL,characters INTEGER NOT NULL)")
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(doc_id UNINDEXED,title,body,tokenize='unicode61')")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
    def import_bytes(self,project,name,raw):
        text=extract(name,raw)
        sha=hashlib.sha256(raw).hexdigest()
        sliced=chunks(text)
        with self.lock,self._db(project) as db:
            existing=db.execute("SELECT id FROM documents WHERE name=?",(name,)).fetchone()
            count=db.execute("SELECT count(*) FROM documents").fetchone()[0]
            if existing is None and count>=MAX_DOCS:raise KnowledgeError("Maximum 50 documents per project.")
            identity=existing[0] if existing else secrets.token_hex(12)
            if existing:
                db.execute("DELETE FROM passages WHERE doc_id=?",(identity,))
                db.execute("DELETE FROM documents WHERE id=?",(identity,))
            db.execute("INSERT INTO documents VALUES(?,?,?,?,?)",(identity,name,sha,datetime.now(timezone.utc).isoformat(),len(text)))
            db.executemany("INSERT INTO passages(doc_id,title,body) VALUES(?,?,?)",[(identity,name,x) for x in sliced])
            return {"id":identity,"name":name,"chunks":len(sliced),"characters":len(text),"replaced":existing is not None}
    def list(self,project):
        with self.lock,self._db(project) as db:
            rows=db.execute("SELECT id,name,uploaded,characters FROM documents ORDER BY uploaded DESC LIMIT 50").fetchall()
        return [dict(zip(("id","name","uploaded","characters"),r)) for r in rows]
    def search(self,project,query,limit=5):
        if not isinstance(query,str) or not query.strip() or len(query)>1000:return []
        words=re.findall(r"[\w]{2,40}",query,flags=re.UNICODE)[:10]
        if not words:return []
        expression=" OR ".join('"'+w.replace('"','')+'"' for w in words)
        with self.lock,self._db(project) as db:
            rows=db.execute("""SELECT doc_id,title,body,bm25(passages) FROM passages
            WHERE passages MATCH ? ORDER BY bm25(passages) LIMIT ?""",(expression,max(1,min(10,limit*3)))).fetchall()
        results=[];seen=set()
        for identity,title,body,_score in rows:
            if identity in seen:continue
            seen.add(identity)
            results.append({"id":identity,"title":title,"excerpt":body[:1100]})
            if len(results)>=limit:break
        return results
    def remove(self,project,identity):
        if not isinstance(identity,str) or not re.fullmatch(r"[a-f0-9]{24}",identity):raise KnowledgeError("Invalid document ID.")
        with self.lock,self._db(project) as db:
            if not db.execute("SELECT 1 FROM documents WHERE id=?",(identity,)).fetchone():
                raise KnowledgeError("Document not found.")
            db.execute("DELETE FROM passages WHERE doc_id=?",(identity,))
            db.execute("DELETE FROM documents WHERE id=?",(identity,))
            return {"deleted":identity}
