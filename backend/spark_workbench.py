"""Owner-gated workspace features independently implemented for SPARK."""
import asyncio
import os

from spark_productivity import Productivity, WorkbenchError, transform_text, text
from spark_office import Office
from spark_robotics import simulate, route
from spark_integrations import Integrations
from spark_intelligence.service import Intelligence, ACTION_KEYS as INTELLIGENCE_ACTIONS
from spark_intelligence.runtime import PolicyError
from spark_vayu_data import VayuExports
from spark_sync import IntegrationSync
from spark_morning_digest import DigestEngine, DigestError, NewsSource
from spark_obsidian_integration import obsidian

ACTION_KEYS = {
    **INTELLIGENCE_ACTIONS,
    "workbench_snapshot": set(),
    "save_preference": {"key", "value"},
    "add_agenda": {"title", "due", "kind"},
    "complete_agenda": {"id", "done"},
    "due_agenda": set(),
    "remove_workbench_item": {"kind", "id"},
    "create_routine": {"title", "steps"},
    "advance_routine": {"id", "approved", "step"},
    "transform_text": {"text", "operation"},
    "create_office": {"format", "spec"},
    "generate_office": {"format", "prompt"},
    "list_artifacts": set(),
    "download_artifact": {"id"},
    "import_pdf": {"name", "data"},
    "pdf_operation": {"ids", "pages", "operation"},
    "simulate_robot": {"spec"},
    "calculate_route": {"start", "end"},
    "list_integrations": set(),
    "mcp_discover": {"server"},
    "mcp_call": {"server", "name", "arguments"},
    "mcp_restart": {"server", "approved"},
    "mcp_audit": set(),
    "analyze_snapshot": {"image", "question"},
    "publish_vayu_snapshot":set(),
    "unpublish_vayu_snapshot":set(),
    "digest_status": set(),
    "digest_run": set(),
    "digest_history": {"limit"},
    "digest_ack": {"digest"},
    "digest_speech": {"digest"},
    "digest_speak": {"digest"},
    "digest_configure": {"schedule_ist", "news_enabled", "news_url"},
}


class Workbench:
    def __init__(self, workspace, integrations=None):
        self.productivity = Productivity(workspace.skills.root.parent, workspace.skills)
        self.office = Office(self.productivity)
        self.integrations = integrations or Integrations(audit_dir=workspace.skills.root.parent/'integrations')
        self.sync = IntegrationSync(workspace.skills.root.parent,
            Integrations(config=getattr(self.integrations,'config',None),audit_dir=workspace.skills.root.parent/'integrations'),local=obsidian.snapshot)
        self.intelligence = Intelligence(workspace,integrations=self.integrations)
        self.vayu = VayuExports(workspace,self.productivity,None)
        self.digest = DigestEngine(workspace.skills.root.parent, self.sync)

    async def execute(self, action, project, payload):
        if action not in ACTION_KEYS or not isinstance(payload, dict) or set(payload) != ACTION_KEYS[action]:
            raise WorkbenchError("Invalid workbench action or arguments.")
        if not isinstance(project, str) or len(project) > 60:
            raise WorkbenchError("Invalid project identifier.")
        self.productivity.skills._file(project)
        if action in ('publish_vayu_snapshot','unpublish_vayu_snapshot'):
            try:
                if action=='unpublish_vayu_snapshot':return await asyncio.to_thread(self.vayu.revoke,project)
                # Runtime SQLite is owned by the event-loop thread. Capture its
                # project rows here before doing snapshot file work off-thread.
                jobs=self.intelligence._runtime().jobs(project)
                return await asyncio.to_thread(self.vayu.publish,project,jobs)
            except ValueError as error:raise WorkbenchError(str(error)) from None
        if action in INTELLIGENCE_ACTIONS:
            if os.environ.get('SPARK_INTELLIGENCE_ENABLED','1')=='0':
                raise WorkbenchError('Optional intelligence module is disabled on this host.')
            try:
                return await self.intelligence.execute(action, project, payload)
            except PolicyError as error:
                raise WorkbenchError(str(error)) from None
        if action=='mcp_restart':
            return await self.integrations.restart(payload['server'],approved=payload['approved'])
        if action=='mcp_audit':return self.integrations.history()
        if action in ("mcp_discover", "mcp_call"):
            arguments = {} if action == "mcp_discover" else {"name": payload["name"], "arguments": payload["arguments"]}
            return await self.integrations.execute(payload["server"], action, arguments)
        if action == "generate_office":
            extension = payload["format"]
            if extension not in ("docx", "xlsx", "pptx", "pdf"):
                raise WorkbenchError("Unsupported office format.")
            prompt = text(payload["prompt"], 2000)
            from spark_evolution import generate_json
            schema = ('{"title":"Title","sheets":[{"name":"Sheet1","rows":[["Item","Value"],["Example",1]],"chart":true}]}'
                      if extension == "xlsx" else
                      '{"title":"Title","sections":[{"heading":"Section","text":"Paragraph","bullets":["Point"],"notes":"Speaker notes"}]}')
            spec = await generate_json("Create original structured office content. Return JSON in exactly this structure: "+schema+
                                       ". At most 12 sections or 5 sheets. Use plain strings and finite numbers. Do not invent verified facts or citations.",
                                       {"request": prompt, "format": extension})
            return await asyncio.to_thread(self._execute, "create_office", project, {"format": extension, "spec": spec})
        if action in ("digest_run", "digest_speak"):
            # One digest per day; speech is a local-only, explicitly
            # requested Windows System.Speech call.
            try:
                if action == "digest_run":
                    return await asyncio.to_thread(self.digest.run)
                return await asyncio.to_thread(self.digest.speak, payload["digest"] or None)
            except DigestError as error:
                raise WorkbenchError(str(error)) from None
        if action == "analyze_snapshot":
            if os.environ.get("SPARK_GROQ_VISION_ENABLED") != "1":
                raise WorkbenchError("Enable SPARK_GROQ_VISION_ENABLED to analyze a selected screenshot or image.")
            from spark_groq import GroqClient, GroqUnavailable
            from spark_camera_frames import validate_camera_frame
            try:
                frame = validate_camera_frame(payload["image"])
            except ValueError:
                raise WorkbenchError("Selected image must be a valid JPEG of at most 2 MB.") from None
            question = text(payload["question"], 400)
            try:
                return {"answer": await GroqClient().vision(question, frame), "retained": False}
            except GroqUnavailable as error:
                raise WorkbenchError(str(error)) from None
        return await asyncio.to_thread(self._execute, action, project, payload)

    def _digest_history(self, limit):
        try:
            return self.digest.history(limit=limit)
        except DigestError as error:
            raise WorkbenchError(str(error)) from None

    def _digest_ack(self, digest):
        try:
            return self.digest.acknowledge(digest or None)
        except DigestError as error:
            raise WorkbenchError(str(error)) from None

    def _digest_speech(self, digest):
        try:
            return self.digest.speech_payload(digest or None)
        except DigestError as error:
            raise WorkbenchError(str(error)) from None

    def _digest_configure(self, data):
        try:
            return self.digest.configure(
                schedule_ist=data["schedule_ist"], news_enabled=data["news_enabled"],
                news_url=data["news_url"] or None)
        except DigestError as error:
            raise WorkbenchError(str(error)) from None

    def _execute(self, action, project, data):
        p, o = self.productivity, self.office
        if action == "digest_status": return self.digest.status()
        if action == "digest_history": return self._digest_history(data["limit"])
        if action == "digest_ack": return self._digest_ack(data["digest"])
        if action == "digest_speech": return self._digest_speech(data["digest"])
        if action == "digest_configure": return self._digest_configure(data)
        try:
            if action == "workbench_snapshot": return p.snapshot(project)
            if action == "save_preference": return p.preference(project, data["key"], data["value"])
            if action == "add_agenda": return p.agenda(project, data["title"], data["due"], data["kind"])
            if action == "complete_agenda": return p.update_agenda(project, data["id"], data["done"])
            if action == "due_agenda": return p.due(project)
            if action == "remove_workbench_item": return p.remove(project, data["kind"], data["id"])
            if action == "create_routine": return p.create_routine(project, data["title"], data["steps"])
            if action == "advance_routine": return p.advance(project, data["id"], data["approved"], data["step"])
            if action == "transform_text": return transform_text(data["text"], data["operation"])
            if action == "create_office": return o.create(project, data["format"], data["spec"])
            if action == "list_artifacts": return o.list(project)
            if action == "download_artifact": return o.download(project, data["id"])
            if action == "import_pdf": return o.import_pdf(project, data["name"], data["data"])
            if action == "pdf_operation": return o.pdf(project, data["ids"], data["pages"], data["operation"])
            if action == "simulate_robot": return simulate(data["spec"])
            if action == "calculate_route": return route(data["start"], data["end"])
            if action == "list_integrations": return self.integrations.list()
        except (KeyError, TypeError, ValueError, OverflowError, ImportError) as error:
            if isinstance(error, WorkbenchError): raise
            if isinstance(error, ImportError):
                raise WorkbenchError("Install the office/MCP dependencies from requirements.txt in SPARK's Python environment.") from None
            raise WorkbenchError("Invalid workbench input or document structure.") from None
        raise WorkbenchError("Unsupported workbench operation.")
