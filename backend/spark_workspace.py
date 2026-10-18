"""SPARK's permission-gated workspace interface to the actual ARKUS engines.

Offline by default; no direct file path exposure, shell execution or model calls.
"""
import re
import os
import secrets
from pathlib import Path
from arkus_knowledge_base import KnowledgeBase, KnowledgeError, MAX_FILE
from arkus_skill_forge import SkillForge, SkillError

_ACTION_KEYS={
    "import_document":{"name","data"},
    "list_documents":set(),
    "search_documents":{"query"},
    "remove_document":{"id"},
    "list_skills":set(),
    "propose_skill":{"spec"},
    "test_skill":{"id"},
    "activate_skill":{"id"},
    "run_skill":{"name","params"},
    "revise_skill":{"id","spec"},
    "rollback_skill":{"id"},
    "publish_holo_note":{"id"},
    "unpublish_holo_note":{"id"},
    "list_holo_notes":set(),
}
_PROJECT=re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

class WorkspaceError(ValueError):
    """Safe, bounded, user-displayable input validation failure."""

class SparkWorkspace:
    def __init__(self,data_dir):
        self.knowledge=KnowledgeBase(data_dir)
        self.skills=SkillForge(data_dir)
        self.holo_notes_root=Path(data_dir).resolve()/"holo-notes"

    def _holo_folder(self,project):
        folder=self.holo_notes_root/project
        if any(p.is_symlink() for p in (self.holo_notes_root,folder)):
            raise WorkspaceError("Linked notes directories are not permitted.")
        return folder

    def _holo_path(self,project,identity):
        if not isinstance(identity,str) or not re.fullmatch(r"[a-f0-9]{24}",identity):
            raise WorkspaceError("Invalid document identifier.")
        folder=self._holo_folder(project)
        path=folder/(identity+".md")
        if path.is_symlink():
            raise WorkspaceError("Linked published notes are not permitted.")
        return path

    def _publish(self,project,identity):
        path=self._holo_path(project,identity)
        # Retrieve only the explicitly selected indexed document, locally.
        with self.knowledge.lock,self.knowledge._db(project) as db:
            item=db.execute("SELECT name FROM documents WHERE id=?",(identity,)).fetchone()
            if item is None:
                raise WorkspaceError("Document not found in this project.")
            chunks=db.execute("SELECT body FROM passages WHERE doc_id=? ORDER BY rowid",(identity,)).fetchall()
        body="\n\n".join(part[0] for part in chunks)[:4000]
        if not body.strip():
            raise WorkspaceError("Document has no readable content.")
        path.parent.mkdir(parents=True,exist_ok=True)
        scratch=path.with_name("."+identity+"."+secrets.token_hex(5)+".tmp")
        try:
            scratch.write_text("# "+item[0]+"\n\n"+body,encoding="utf-8")
            os.replace(scratch,path)
        finally:
            scratch.unlink(missing_ok=True)
        return {"published":True,"id":identity,"name":item[0]}

    def _published(self,project):
        folder=self._holo_folder(project)
        if not folder.is_dir():return []
        docs={doc["id"]:doc["name"] for doc in self.knowledge.list(project)}
        results=[]
        for identity,name in docs.items():
            path=self._holo_path(project,identity)
            if path.is_file():
                results.append({"id":identity,"name":name})
        return results

    def _unpublish(self,project,identity):
        path=self._holo_path(project,identity)
        if not path.is_file():
            raise WorkspaceError("Document is not published to HOLO.")
        path.unlink()
        return {"published":False,"id":identity}


    def execute(self,action,project,data):
        if not isinstance(action,str) or action not in _ACTION_KEYS:
            raise WorkspaceError("Workspace action is not supported.")
        if not isinstance(project,str) or not _PROJECT.fullmatch(project) or len(project)>60:
            raise WorkspaceError("Use a valid project identifier.")
        if not isinstance(data,dict) or set(data)!=_ACTION_KEYS[action]:
            raise WorkspaceError("Workspace request arguments are invalid.")
        try:
            if action=="import_document":
                blob=data["data"]
                if not isinstance(blob,bytes) or not 0<len(blob)<=MAX_FILE:
                    raise WorkspaceError("Selected document must be 1 byte to 2 MB.")
                return self.knowledge.import_bytes(project,data["name"],blob)
            if action=="list_documents":
                return self.knowledge.list(project)
            if action=="search_documents":
                return self.knowledge.search(project,data["query"])
            if action=="remove_document":
                return self.knowledge.remove(project,data["id"])
            if action=="list_holo_notes":
                return self._published(project)
            if action=="publish_holo_note":
                return self._publish(project,data["id"])
            if action=="unpublish_holo_note":
                return self._unpublish(project,data["id"])
            if action=="list_skills":
                return self.skills.available(project)
            if action=="propose_skill":
                return self.skills.propose(data["spec"],project)
            if action=="test_skill":
                return self.skills.test(project,data["id"])
            if action=="activate_skill":
                return self.skills.activate(project,data["id"])
            if action=="run_skill":
                return self.skills.run(project,data["name"],data["params"])
            if action=="revise_skill":
                return self.skills.revise(project,data["id"],data["spec"])
            if action=="rollback_skill":
                return self.skills.rollback(project,data["id"])
        except (KnowledgeError,SkillError,KeyError,TypeError,ValueError) as exc:
            raise WorkspaceError(str(exc)[:200]) from None
        raise WorkspaceError("Unsupported workspace operation.")
