"""SPARK's permission-gated workspace interface to the actual ARKUS engines.

Offline by default; no direct file path exposure, shell execution or model calls.
"""
import re
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
}
_PROJECT=re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

class WorkspaceError(ValueError):
    """Safe, bounded, user-displayable input validation failure."""

class SparkWorkspace:
    def __init__(self,data_dir):
        self.knowledge=KnowledgeBase(data_dir)
        self.skills=SkillForge(data_dir)

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
