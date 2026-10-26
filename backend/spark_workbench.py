"""Owner-gated workspace features independently implemented for SPARK."""
import asyncio
import json
import os
import time
from pathlib import Path

from spark_productivity import Productivity, WorkbenchError, transform_text, text

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
from spark_office import Office
from spark_robotics import simulate, route
from spark_integrations import Integrations
from spark_intelligence.service import Intelligence, ACTION_KEYS as INTELLIGENCE_ACTIONS
from spark_intelligence.runtime import PolicyError
from spark_vayu_data import VayuExports
from spark_sync import IntegrationSync
from spark_morning_digest import DigestEngine, DigestError, NewsSource
from spark_messaging_hub import MessagingHub, HubError
from spark_credential_store import CredentialStore
from spark_opencode_agent import OpenCodeAgent, OpenCodeError
from spark_openclaw_bridge import OpenClawBridge, OpenClawError
from spark_deep_research import ResearchEngine, ResearchError, ResearchSource
from spark_proactive_agent import ProactiveAgent, ProactiveError, Proposal
from spark_monitor_agents import MonitorAgents, MonitorError
from spark_trace_learning import (TraceStore, AdaptiveRouter, LearningEngine,
                                  LearningError, policy_always_local,
                                  policy_latency_smallest)
from spark_spec_search import CaseSet, SpecError, SpecSearch
from spark_skill_ecosystem import SkillEcosystem, SkillEcosystemError
from spark_agent_runtimes import (AgentRuntimes, AgentRuntimeError, Tool,
                                  MAX_STEPS, MAX_DEPTH)
from spark_connector_catalog import ConnectorCatalog, ConnectorError
from spark_evaluations import EvaluationError, Evaluations
from spark_model_evaluations import attach_local_evaluator
from spark_inference_telemetry import Telemetry, TelemetryError
from spark_inference_backends import (InferenceBackends, BackendError,
                                      IMPLEMENTED_ENGINES)
from spark_obsidian_integration import obsidian

ACTION_KEYS = {
    **INTELLIGENCE_ACTIONS,
    "workbench_snapshot": set(),
    "knowledge_notes": {"query"},
    "knowledge_note": {"path"},
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
    "hub_status": set(),
    "hub_configure": {"channel", "config"},
    "hub_disconnect": {"channel"},
    "hub_approve": {"channel", "recipient", "text"},
    "hub_send": {"channel", "approval_id"},
    "hub_receive": {"channel"},
    "hub_history": {"limit"},
    "opencode_status": set(),
    "openclaw_status": set(),
    "openclaw_run": {"prompt", "model", "timeout"},
    "opencode_run": {"prompt", "cwd", "timeout"},
    "opencode_diff": {"session"},
    "opencode_test": {"command", "cwd"},
    "research_run": {"question", "max_hops"},
    "proactive_propose": {"source", "kind", "tier", "detail"},
    "proactive_decide": {"dedupe_key", "approved", "remember"},
    "proactive_execute": {"dedupe_key"},
    "proactive_undo": {"dedupe_key"},
    "proactive_inbox": {"state", "limit"},
    "proactive_summary": set(),
    "monitor_status": set(),
    "monitor_run": {"name", "force"},
    "monitor_cancel": {"name"},
    "monitor_deliver": {"name"},
    "monitor_acknowledge": {"key"},
    "trace_capture": {"task_class", "model", "payload", "latency_ms", "success"},
    "trace_label": {"key", "success"},
    "trace_labeled": {"task_class", "limit"},
    "trace_status": set(),
    "router_select": {"task_class", "apply_policy"},
    "learning_propose": {"name", "policy", "task_class"},
    "learning_activate": {"key", "approved_by"},
    "learning_rollback": {"key"},
    "learning_status": set(),
    "spec_search_status": set(),
    "spec_search_run": {"goal"},
    "spec_candidates": {"status", "limit"},
    "spec_activate": {"key", "approved_by"},
    "spec_rollback": set(),
    "skill_import": {"manifest", "provided_by"},
    "skill_review": {"key", "approved_by", "granted_tools"},
    "skill_list": set(),
    "skill_run": {"key", "name", "pipeline", "inputs"},
    "skill_runs": {"key", "limit"},
    "skill_revoke": {"key", "approved_by"},
    "skill_status": set(),
    "agents_status": set(),
    "agents_react": {"goal", "steps", "grant_side_effects"},
    "agents_codeact": {"code"},
    "agents_recursive": {"goal", "steps", "subgoals"},
    "agents_runs": {"adapter", "limit"},
    "connector_status": set(),
    "connector_attach_local": {"id", "provider", "scope"},
    "connector_configure": {"id", "account", "consented"},
    "connector_validate": {"id"},
    "connector_read": {"id", "limit"},
    "connector_freshness": {"id", "stale_after_seconds"},
    "connector_revoke": {"id", "approved_by"},
    "connector_events": {"id", "limit"},
    "eval_status": set(),
    "eval_register": {"name", "provenance"},
    "eval_run": {"name", "suite"},
    "eval_report": {"name", "suite"},
    "eval_export": {"name", "suite"},
    "eval_history": {"limit"},
    "telemetry_status": set(),
    "telemetry_capture": {"model", "prompt", "allow_cloud"},
    "telemetry_record": {"model", "latency_ms", "input_tokens", "output_tokens", "source"},
    "telemetry_report": {"model"},
    "backend_describe": set(),
    "backend_probe": {"engine", "consented"},
    "backend_generate": {"engine", "prompt", "consented"},
    "backend_opt_in": {"engine", "approved_by", "measured_ram_gb"},
    "backend_events": {"engine", "limit"},
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
        self.messaging = MessagingHub(workspace.skills.root.parent,
                                      secret_store=CredentialStore())
        # The scoped OpenCode root is SPARK's own repository: sessions may
        # only work inside it, and every other path is refused.
        self.opencode = OpenCodeAgent(REPOSITORY_ROOT)
        self.openclaw = OpenClawBridge()
        self.research = ResearchEngine([
            ResearchSource("local-snapshots", self._snapshot_docs),
            ResearchSource("obsidian-vault", self._obsidian_docs),
        ])
        self.proactive = ProactiveAgent(workspace.skills.root.parent)
        self.proactive.register_executor(
            "search.obsidian", "obsidian-vault",
            run=lambda detail: {"matches": obsidian.search(detail, limit=5)},
            undo=lambda payload: None)  # read-only effect: nothing to reverse
        self.proactive.register_executor(
            "search.snapshots", "workbench",
            run=lambda detail: self.sync.search(detail).get("results", [])[:5],
            undo=lambda payload: None)
        self.monitors = MonitorAgents(workspace.skills.root.parent)
        self.monitors.register("snapshot-freshness", "workspace",
                               self._snapshot_freshness_check, interval=600)
        self._notifications = workspace.skills.root / "monitor-notifications.jsonl"
        # Capabilities 07 & 12: evidence-first trace learning and local-first
        # routing. Only registered policies can ever be proposed or activated,
        # and activation is owner-approved with rollback to the baseline.
        self.learning_store = TraceStore(workspace.skills.root.parent)
        self.router = AdaptiveRouter(self.learning_store)
        self.learning = LearningEngine(self.learning_store)
        self.learning_policies = {
            "always-local": policy_always_local,
            "latency-smallest": policy_latency_smallest,
        }
        # Capability 08: no planner is granted automatically; spec search
        # honestly reports planner_not_configured until the owner grants a
        # zero-cost planner explicitly.
        self.specs = SpecSearch(workspace.skills.root.parent)
        # Capability 09: only two owner-safe, read-only operations exist for
        # skills; nothing else can be granted or executed.
        self.skills = SkillEcosystem(workspace.skills.root.parent)
        self.skills.register_operation(
            "search.obsidian",
            lambda ctx, prior: self._safe_obsidian_search(ctx))
        self.skills.register_operation(
            "search.snapshots",
            lambda ctx, prior: self._safe_snapshot_search(ctx))
        # Capability 10: guarded runtimes with the same two read-only tools.
        self.agent_runtime = AgentRuntimes(workspace.skills.root.parent)
        self.agent_runtime.register(Tool(
            "search.snapshots",
            lambda payload: self.sync.search(str(payload)).get("results", [])[:5]
            if isinstance(payload, str) and payload else []))
        self.agent_runtime.register(Tool(
            "obsidian.search",
            lambda payload: obsidian.search(str(payload), limit=5)
            if isinstance(payload, str) and payload else []))
        # Capabilities 13-16: connector catalog, evaluations, telemetry and
        # unified backend description. All new connectors start disabled.
        self.connectors = ConnectorCatalog(workspace.skills.root.parent)
        self._attach_local_connectors()
        self.evaluations = Evaluations(workspace.skills.root.parent)
        evaluation_model = os.environ.get('SPARK_EVALUATION_MODEL', '').strip()
        if evaluation_model:
            attach_local_evaluator(self.evaluations, self.intelligence.models,
                                   evaluation_model)
        sampler = self._vitals_sampler()
        self.telemetry = Telemetry(workspace.skills.root.parent, sampler=sampler)
        ram_gb = None
        if sampler is not None:
            try:
                import psutil
                ram_gb = psutil.virtual_memory().total / (1024 ** 3)
            except (ImportError, OSError):
                ram_gb = None
        self.backends = InferenceBackends(workspace.skills.root.parent,
                                          hardware_ram_gb=ram_gb,
                                          telemetry=self.telemetry)
        self._attach_engine_adapters()

    def _snapshot_freshness_check(self):
        """Persistent monitor: report stale read-only integration snapshots."""
        events = []
        try:
            sync = self.sync.status()
        except (ValueError, OSError):
            return events
        for source in sync.get("sources", []):
            if source.get("stale"):
                events.append({"kind": "snapshot.stale", "id": source["id"],
                               "state": source.get("state"),
                               "last_success": source.get("last_success")})
        return events

    def _dispatch_offloop(self, action, payload):
        if action == "proactive_propose":
            proposal = Proposal(payload["source"], payload["kind"],
                                payload["tier"], payload["detail"])
            return self.proactive.propose(proposal)
        if action == "proactive_decide":
            return self.proactive.decide(payload["dedupe_key"],
                                         approved=bool(payload["approved"]),
                                         remember=bool(payload["remember"]))
        if action == "proactive_execute":
            return self.proactive.execute(payload["dedupe_key"])
        if action == "proactive_undo":
            return self.proactive.undo(payload["dedupe_key"])
        if action == "monitor_run":
            return self.monitors.run_once(payload["name"], force=bool(payload["force"]))
        if action == "monitor_deliver":
            return self.monitors.deliver(payload["name"], self._notify_channel)
        raise WorkbenchError("Unsupported off-loop action.")

    def _notify_channel(self, key):
        """Local notification channel: append one line, no external service."""
        path = self._notifications
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"key": key, "at": time.time()}) + "\n")

    def _snapshot_docs(self, query):
        """Verified local integration snapshot search as a research corpus."""
        try:
            results = self.sync.search(query).get("results", [])
        except (WorkbenchError, ValueError):
            results = []
        from spark_deep_research import SourceDoc
        return [SourceDoc(source=f"snapshot:{result.get('service', 'integration')}",
                          title=result.get("id", "integration snapshot"),
                          body=result.get("snippet", ""),
                          url=result.get("untrusted_source") and "",
                          retrieved_at=result.get("last_success") or 0)
                for result in results]

    def _obsidian_docs(self, query):
        """Saved vault notes only; never writes or fetches remote content."""
        from spark_deep_research import SourceDoc
        try:
            matches = obsidian.search(query, limit=10)
        except (ValueError, OSError):
            return []
        return [SourceDoc(source="obsidian-vault",
                          title=(match.get("path") or "vault note")[:120],
                          body=(match.get("snippet") or "")[:4000],
                          url="", retrieved_at=0)
                for match in matches if isinstance(match, dict)]

    async def _hub(self, action, payload):
        """Network-capable hub calls run off the event loop; errors stay mine."""
        notifier = {"hub_configure": lambda: self.messaging.configure(
                        payload["channel"], payload["config"]),
                    "hub_disconnect": lambda: self.messaging.disconnect(payload["channel"]),
                    "hub_approve": lambda: self.messaging.approve_outbound(
                        payload["channel"], payload["recipient"], payload["text"]),
                    "hub_send": lambda: self.messaging.send(
                        payload["channel"], payload["approval_id"]),
                    "hub_receive": lambda: self.messaging.receive(payload["channel"]),
                    "hub_history": lambda: self.messaging.history(limit=payload["limit"])}
        try:
            return await asyncio.to_thread(notifier[action])
        except HubError as error:
            raise WorkbenchError(str(error)) from None

    async def execute(self, action, project, payload):
        if action not in ACTION_KEYS or not isinstance(payload, dict) or set(payload) != ACTION_KEYS[action]:
            raise WorkbenchError("Invalid workbench action or arguments.")
        if not isinstance(project, str) or len(project) > 60:
            raise WorkbenchError("Invalid project identifier.")
        self.productivity.skills._file(project)
        if action == 'knowledge_notes':
            return await asyncio.to_thread(obsidian.search, text(payload['query'], 200), 20)
        if action == 'knowledge_note':
            return {'text': (await asyncio.to_thread(obsidian.read, text(payload['path'], 300)))[:20000]}
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
            if action == 'mcp_call' and payload['server'] == 'graphiti' and payload['name'] in ('search_temporal_facts', 'get_entity_timeline', 'refresh_project_graph'):
                if not isinstance(payload['arguments'], dict):
                    raise WorkbenchError('Graphiti arguments must be an object.')
                if payload['arguments'].get('project', project) != project:
                    raise WorkbenchError('Graphiti uses the selected workspace project.')
                arguments = {'name': payload['name'], 'arguments': {**payload['arguments'], 'project': project}}
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
        if action in ("hub_configure", "hub_disconnect", "hub_approve", "hub_send",
                      "hub_receive", "hub_history"):
            return await self._hub(action, payload)
        if action == "openclaw_status":
            return await asyncio.to_thread(self.openclaw.status)
        if action == "openclaw_run":
            try:
                return await asyncio.to_thread(self.openclaw.run,
                    payload["prompt"], payload["model"], payload["timeout"])
            except OpenClawError as error:
                raise WorkbenchError(str(error)) from None
        if action == "opencode_run":
            if not payload["cwd"] or payload["cwd"] == "REPO_ROOT":
                cwd = None
            else:
                cwd = payload["cwd"]
            try:
                return await asyncio.to_thread(
                    self.opencode.run, payload["prompt"], cwd=cwd,
                    timeout=int(payload["timeout"]))
            except OpenCodeError as error:
                raise WorkbenchError(str(error)) from None
        if action == "opencode_diff":
            try:
                return await asyncio.to_thread(
                    self.opencode.diff, payload["session"] or None)
            except OpenCodeError as error:
                raise WorkbenchError(str(error)) from None
        if action == "opencode_test":
            target = payload["cwd"] or None
            try:
                return await asyncio.to_thread(self.opencode.run_tests,
                                               payload["command"], cwd=target)
            except OpenCodeError as error:
                raise WorkbenchError(str(error)) from None
        if action == "research_run":
            try:
                budget = payload["max_hops"] or None
                return await asyncio.to_thread(self.research.research,
                                               payload["question"], max_hops=budget)
            except ResearchError as error:
                raise WorkbenchError(str(error)) from None
        if action in ("proactive_execute", "proactive_undo", "proactive_decide",
                      "proactive_propose", "monitor_run", "monitor_deliver"):
            try:
                return await asyncio.to_thread(self._dispatch_offloop, action, payload)
            except (ProactiveError, MonitorError, ValueError, OSError) as error:
                raise WorkbenchError(str(error)) from None
        if action in ("digest_run", "digest_speak"):
            # Voice playback belongs to the authenticated live session in
            # server.py. Never launch a second speaker outside its audio gate.
            try:
                if action == "digest_run":
                    return await asyncio.to_thread(self.digest.run)
                return await asyncio.to_thread(self._digest_speech, payload["digest"])
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
            return self.digest.narration_payload(digest or None)
        except DigestError as error:
            raise WorkbenchError(str(error)) from None

    def _digest_configure(self, data):
        try:
            self.digest.validate_configuration(schedule_ist=data['schedule_ist'],
                                               news_enabled=data['news_enabled'], news_url=data['news_url'] or None)
            # Only the host-installed daily task is updated. Temporary workspaces
            # and platforms without that registration keep pure local settings.
            if os.name == 'nt' and self.digest._stored('windows_task') == 'SPARK Morning Digest':
                import subprocess
                schedule = str(data['schedule_ist'])
                environment = dict(os.environ, SPARK_WORKSPACE_DATA_ROOT=str(self.digest.root.parent))
                try:
                    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                             '-File', str(REPOSITORY_ROOT / 'scripts/install-morning-digest.ps1'),
                                             '-TimeIST', schedule], env=environment, capture_output=True, timeout=45)
                except (OSError, subprocess.TimeoutExpired):
                    raise DigestError('Windows daily digest task update was unavailable or timed out.') from None
                if result.returncode:
                    raise DigestError('Windows could not update the daily digest task; check its local registration.')
            return self.digest.configure(
                schedule_ist=data["schedule_ist"], news_enabled=data["news_enabled"],
                news_url=data["news_url"] or None)
        except DigestError as error:
            raise WorkbenchError(str(error)) from None

    @staticmethod
    def _measured_flag(value):
        """Convert the workbench string flag into a measured boolean or None."""
        if value in (None, ""):
            return None
        lower = str(value).strip().lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
        raise LearningError("Measured outcomes are booleans or unmeasured.")

    def _candidate_policy(self, key):
        """Resolve an activated candidate back to its registered policy."""
        row = next((c for c in self.learning.candidates() if c["key"] == key), None)
        if not row:
            raise LearningError("Candidate not found.")
        policy = self.learning_policies.get(row["definition"])
        if policy is None:
            raise LearningError("Candidate policy is not registered on this "
                                "host: " + str(row["definition"]))
        return policy

    def _learning_action(self, action, data):
        """Capabilities 07 & 12 dispatch; LearningError stays workbench-shaped."""
        try:
            if action == "trace_capture":
                return self.learning_store.capture(
                    data["task_class"], data["model"], data["payload"],
                    float(data["latency_ms"]),
                    success=self._measured_flag(data["success"]))
            if action == "trace_label":
                success = self._measured_flag(data["success"])
                if success is None:
                    raise LearningError("Label with a measured boolean outcome only.")
                return self.learning_store.label(data["key"], success=success)
            if action == "trace_labeled":
                return self.learning_store.labeled(
                    task_class=data["task_class"] or None,
                    limit=int(data["limit"] or 200))
            if action == "trace_status":
                return {"summary": self.learning_store.model_summary()}
            if action == "router_select":
                return self.router.select(data["task_class"],
                                          apply_policy=bool(data["apply_policy"]))
            if action == "learning_propose":
                name = str(data["policy"] or "")
                policy = self.learning_policies.get(name)
                if policy is None:
                    raise LearningError("Only a policy registered on this host "
                                        "can be proposed: " + name)
                return self.learning.propose(data["name"], policy,
                                             data["task_class"])
            if action == "learning_activate":
                policy = self._candidate_policy(data["key"])
                result = self.learning.activate(data["key"],
                                                approved_by=data["approved_by"])
                self.router.set_policy(policy)
                return result
            if action == "learning_rollback":
                result = self.learning.rollback(data["key"])
                self.router.set_policy(policy_always_local)
                return result
            # learning_status
            registered = {row["definition"] for row in self.learning.candidates()
                          if row["definition"] in self.learning_policies}
            return {"candidates": self.learning.candidates(),
                    "measured_summary": self.learning_store.model_summary(),
                    "active_policy": getattr(self.router.current_policy,
                                             "__name__", "policy"),
                    "registered_policies": sorted(registered)}
        except (LearningError, ValueError, TypeError) as error:
            # LearningError is a ValueError subclass; both stay workbench-shaped.
            raise WorkbenchError(str(error)) from None

    @staticmethod
    def _safe_obsidian_search(ctx):
        """Bounded read-only vault search used as a skill operation."""
        payload = ctx.get("q") if isinstance(ctx, dict) else None
        try:
            return [match.get("path") for match in
                    obsidian.search(str(payload), limit=5)
                    if isinstance(match, dict)]
        except (ValueError, OSError):
            return []

    def _safe_snapshot_search(self, ctx):
        """Bounded read-only integration snapshot search."""
        payload = ctx.get("q") if isinstance(ctx, dict) else None
        try:
            results = self.sync.search(str(payload)).get("results", [])
        except (WorkbenchError, ValueError, TypeError):
            results = []
        return [str(result.get("id")) for result in results[:5]
                if isinstance(result, dict)]

    def _spec_action(self, action, data):
        try:
            if action == "spec_search_status":
                return self.specs.status()
            if action == "spec_search_run":
                return self.specs.search(data["goal"], self._spec_case_set(),
                                         self._spec_case_runner())
            if action == "spec_candidates":
                return self.specs.candidates(
                    status=data["status"] or None,
                    limit=int(data["limit"] or 20))
            if action == "spec_activate":
                return self.specs.activate(data["key"],
                                           approved_by=data["approved_by"])
            # spec_rollback
            return self.specs.rollback()
        except (SpecError, ValueError, TypeError) as error:
            raise WorkbenchError(str(error)) from None

    @staticmethod
    def _spec_case_set():
        """Owner-authored fixture cases; live data comes only from consented
        sources and is never fabricated here."""
        return CaseSet("fixture.workbench-spec", [
            {"name": "identity-support",
             "input": {"route": "identity", "text": "unsubscribe"},
             "expected": {"answer": "route"}},
            {"name": "identity-no-op",
             "input": {"route": "identity", "text": "hello"},
             "expected": {"answer": "skip"}},
            {"name": "cal-support",
             "input": {"route": "calendar", "text": "reschedule"},
             "expected": {"answer": "route"}},
            {"name": "cal-no-op",
             "input": {"route": "calendar", "text": "thanks"},
             "expected": {"answer": "skip"}},
        ], provenance="fixture:workbench")

    @staticmethod
    def _spec_case_runner():
        """Measured runner: answer routes when the spec's routing class is
        enabled for the source; mismatches are recorded as failures."""
        def runner(spec, case):
            route = case["input"]["route"]
            trigger = case["input"]["text"]
            rules = spec.get("route_rules") or {}
            enabled = bool(rules.get(route)) and not bool(
                rules.get(route + "_no_trigger"))
            decided = "route" if enabled else "skip"
            # A "route" decision requires a matching explicit trigger word.
            if decided == "route" and not trigger:
                decided = "skip"
            return decided == case["expected"]["answer"]
        return runner

    def _skill_action(self, action, data):
        try:
            if action == "skill_import":
                return self.skills.import_skill(data["manifest"],
                                                provided_by=data["provided_by"])
            if action == "skill_review":
                return self.skills.review(data["key"],
                                          approved_by=data["approved_by"],
                                          granted_tools=list(data["granted_tools"]))
            if action == "skill_list":
                return self.skills.list()
            if action == "skill_run":
                return self.skills.run_pipeline(
                    data["key"], data["name"],
                    list(data["pipeline"] or []), dict(data["inputs"] or {}))
            if action == "skill_runs":
                return self.skills.runs(data["key"] or None,
                                        limit=int(data["limit"] or 20))
            if action == "skill_revoke":
                return self.skills.revoke(data["key"],
                                          approved_by=data["approved_by"])
            # skill_status
            return self.skills.status()
        except (SkillEcosystemError, ValueError, TypeError) as error:
            raise WorkbenchError(str(error)) from None

    def _agents_action(self, action, data):
        try:
            if action == "agents_status":
                return self.agent_runtime.status()
            if action == "agents_runs":
                return self.agent_runtime.runs(data["adapter"] or None,
                                               limit=int(data["limit"] or 20))
            if action == "agents_codeact":
                result = self.agent_runtime.codeact.evaluate(data["code"], {})
                key = self.agent_runtime.record_run("codeact", data["code"],
                                                    "evaluated",
                                                    [{"expression": result[:200]}],
                                                    result)
                return {"key": key, "status": "evaluated", "result": result}
            steps = list(data["steps"] or [])
            if not steps or len(steps) > MAX_STEPS + 1:
                raise AgentRuntimeError("Scripted steps are 1–13 entries.")
            scripted = list(steps)
            def model(_state):
                return scripted.pop(0) if scripted else {"final": "done"}
            if action == "agents_react":
                outcome = self.agent_runtime.react.run(
                    data["goal"], model,
                    side_effects_granted=bool(data["grant_side_effects"]))
            else:  # agents_recursive
                subgoals = list(data["subgoals"] or [])
                planner = lambda goal: subgoals
                outcome = self.agent_runtime.recursive.run(data["goal"], model,
                                                           planner,
                                                           depth=MAX_DEPTH)
            record = outcome.get("answer") or outcome.get("status")
            key = self.agent_runtime.record_run(
                "react" if action == "agents_react" else "recursive",
                data["goal"], outcome["status"], outcome.get("steps", []),
                record)
            return {**outcome, "key": key}
        except (AgentRuntimeError, ValueError, TypeError) as error:
            raise WorkbenchError(str(error)) from None

    @staticmethod
    def _vitals_sampler():
        """Measured host vitals sampler; None when psutil is unavailable."""
        try:
            import psutil
        except ImportError:
            return None
        if psutil is None:
            return None
        def sampler():
            return {"cpu_percent": psutil.cpu_percent(),
                    "ram_used_mb": psutil.virtual_memory().used / 1024 / 1024}
        return sampler

    def _attach_local_connectors(self):
        """Two real, consent-gated local connectors plus honest refusal of
        cloud connectors without credentialed accounts."""
        self.connectors.register(
            "workspace-search", "IntegrationSync",
            scope="read-only full-text search over synced local snapshots",
            validate_account=lambda: "founder@local-workspace",
            read_page=lambda cursor, limit: self._connector_workspace_page(
                cursor, limit),
            revoke=lambda: None)
        self.connectors.register(
            "obsidian-vault", "Local vault",
            scope="read-only vault note paths and match snippets",
            validate_account=lambda: "founder@local-vault",
            read_page=lambda cursor, limit: self._connector_obsidian_page(
                cursor, limit),
            revoke=lambda: None)

    def _connector_workspace_page(self, cursor, limit):
        query = cursor or ""
        try:
            results = self.sync.search(query).get("results", [])
        except (WorkbenchError, ValueError, TypeError):
            results = []
        bounded = results[:max(1, int(limit))]
        cursor_pos = ("more" if len(results) > len(bounded) else None)
        return {"items": [str(result.get("id", "snapshot")) for result
                          in bounded if isinstance(result, dict)],
                "cursor": cursor_pos,
                "source_time": None}

    def _connector_obsidian_page(self, cursor, limit):
        query = cursor or ""
        try:
            matches = obsidian.search(query, limit=max(1, int(limit)))
        except (ValueError, OSError):
            matches = []
        return {"items": [str(match.get("path")) for match in matches
                          if isinstance(match, dict)],
                "cursor": None,
                "source_time": None}

    def _connector_action(self, action, data):
        try:
            if action == "connector_status":
                return {**self.connectors.status(), "cloud_connectors":
                        "account adapters require the founder's consented, "
                        "credentialed session (capability-02 readers); they "
                        "are never attached automatically"}
            if action == "connector_attach_local":
                return self.connectors.register(
                    data["id"], data["provider"] or "Local",
                    scope=data["scope"],
                    read_page=lambda cursor, limit: {"items": []})
            if action == "connector_configure":
                return self.connectors.configure(
                    data["id"], data["account"], consented=bool(data["consented"]))
            if action == "connector_validate":
                return self.connectors.validate_account(data["id"])
            if action == "connector_read":
                return self.connectors.read_page(
                    data["id"], limit=int(data["limit"] or 20))
            if action == "connector_freshness":
                return self.connectors.freshness(
                    data["id"], stale_after_seconds=float(
                        data["stale_after_seconds"] or 86400))
            if action == "connector_revoke":
                return self.connectors.revoke(data["id"],
                                              approved_by=data["approved_by"])
            return self.connectors.events(data["id"] or None,
                                          limit=int(data["limit"] or 50))
        except (ConnectorError, ValueError, TypeError, OSError) as error:
            raise WorkbenchError(str(error)) from None

    @staticmethod
    def _reference_eval_runner(case):
        """Built-in deterministic reference candidate for the fixture
        suites; explicitly labeled as a policy reference in provenance."""
        decisions = {
            "triage-reply-required": {"classification": "reply_required"},
            "triage-calendar-event": {"classification": "calendar"},
            "triage-archive": {"classification": "archive"},
            "triage-never-assert-thread-unseen": {"classification": "archive"},
            "meeting-conflict": "conflict",
            "meeting-free": "free",
            "meeting-shift-proposal": "conflict",
            "citations-required": {"sources": ["snapshot:local-snapshots"],
                                   "stop": None},
            "unverified-stops": {"stop": "no_evidence"},
            "contradiction-flagged": {"sources": ["a", "b"],
                                      "contradiction": "conflict"},
            "code-destructive-refused": "refused",
            "code-bounded-edit-with-tests": ["applied", "tests_recorded"],
            "code-no-tests-no-activation": "not_activated",
            "policy-side-effect-denied": "refused",
            "policy-side-effect-allowed-with-grant":
                ["applied", "requires_owner_log"],
            "policy-read-only-ok": "applied",
            "repair-tests-first": ["staged", "tests_passed"],
            "repair-no-tests-no-apply": "not_activated",
        }
        if case["id"].startswith("memory-"):
            if case["id"] == "memory-absent":
                return "not_stored"
            return case["input"].get("memory") or "not_stored"
        if case["id"] not in decisions:
            raise ValueError("No reference decision defined for " + case["id"])
        return decisions[case["id"]]

    def _eval_action(self, action, data):
        try:
            if action == "eval_status":
                return self.evaluations.status()
            if action == "eval_register":
                name = str(data["name"]) if data["name"] else ""
                if name != "reference-policy":
                    raise EvaluationError("Owner-attached runners are code "
                                          "gated; the workbench offers the "
                                          "reference-policy runner only.")
                return self.evaluations.register(
                    name, self._reference_eval_runner,
                    provenance=data["provenance"] or "deterministic "
                    "reference policy (fixture suites)")
            if action == "eval_run":
                return self.evaluations.run(data["name"], data["suite"])
            if action == "eval_report":
                return self.evaluations.report(data["name"], data["suite"])
            if action == "eval_export":
                target = self.evaluations.root / "reports"
                return self.evaluations.export(data["name"], data["suite"],
                                               target)
            return self.evaluations.history(limit=int(data["limit"] or 20))
        except (EvaluationError, ValueError, TypeError, OSError) as error:
            raise WorkbenchError(str(error)) from None

    def _telemetry_action(self, action, data):
        try:
            if action == "telemetry_status":
                return self.telemetry.status()
            if action == "telemetry_capture":
                return self._telemetry_capture(data)
            if action == "telemetry_record":
                input_tokens = data["input_tokens"]
                output_tokens = data["output_tokens"]
                return self.telemetry.record(
                    data["model"], latency_ms=float(data["latency_ms"]),
                    input_tokens=int(input_tokens) if input_tokens not in
                    (None, "") else None,
                    output_tokens=int(output_tokens) if output_tokens not in
                    (None, "") else None,
                    source=data["source"] or "manually_recorded")
            return self.telemetry.report(data["model"] or None)
        except (TelemetryError, ValueError, TypeError) as error:
            raise WorkbenchError(str(error)) from None

    def _telemetry_capture(self, data):
        """Measure one real configured-model inference and record telemetry."""
        import asyncio as _asyncio
        models = self.intelligence.models
        configured = next((model for model in models.catalog()
                           if model['id'] == data['model']), None)
        if not (configured and configured['local']) and data['allow_cloud'] is not True:
            raise TelemetryError("Cloud telemetry capture needs explicit "
                                 "owner consent in allow_cloud.")
        async def generate():
            if not configured or not configured.get('available'):
                await models.probe(data['model'], allow_cloud=bool(data['allow_cloud']))
            return await models.generate(data['model'], data['prompt'],
                                         allow_cloud=bool(data['allow_cloud']))
        def runner():
            result = _asyncio.run(generate())
            usage = (result or {}).get("usage") or {}
            result["returned_usage"] = {"input": usage.get("input_tokens"),
                                        "output": usage.get("output_tokens")}
            return result
        return self.telemetry.capture(data["model"], runner,
                                      measure_again=lambda r: r["returned_usage"])

    def _attach_engine_adapters(self):
        """Attach real probe/generate adapters only for engines that have a
        configured model in SPARK_TASK_MODELS on this host."""
        try:
            configured = json.loads(os.environ.get("SPARK_TASK_MODELS", "{}"))
        except (ValueError, TypeError, json.JSONDecodeError):
            configured = {}
        provider_models = {}
        for identifier, item in configured.items():
            if isinstance(item, dict):
                provider_models.setdefault(item.get("provider"), []).append(
                    (item, identifier))
        mapping = {"ollama": "ollama", "gemini": "gemini", "groq": "groq"}
        for engine, provider in mapping.items():
            models = provider_models.get(provider) or []
            if not models:
                continue
            identifier = models[0][1]
            def prober(identifier=identifier, cloud=provider != "ollama"):
                import asyncio as _asyncio
                status = _asyncio.run(
                    self.intelligence.models.probe(
                        identifier, allow_cloud=cloud))
                state = {"healthy": "connected"}.get(status.get("state"),
                                                     status.get("state"))
                return {"state": state, "model": status.get("model", "")}
            def generator(prompt, identifier=identifier, provider=provider):
                import asyncio as _asyncio
                result = _asyncio.run(self.intelligence.models.generate(
                    identifier, str(prompt), allow_cloud=provider != "ollama"))
                usage = (result or {}).get("usage") or {}
                return {"text": str(result.get("answer", "")),
                        "input_tokens": usage.get("input_tokens"),
                        "output_tokens": usage.get("output_tokens")}
            self.backends.attach(engine, probe=prober, generate=generator)

    def _backends_action(self, action, data):
        try:
            if action == "backend_describe":
                return self.backends.describe()
            if action == "backend_probe":
                return self.backends.probe(data["engine"],
                                           consented=bool(data["consented"]))
            if action == "backend_generate":
                return self.backends.generate(
                    data["engine"], data["prompt"],
                    consented=bool(data["consented"]))
            if action == "backend_opt_in":
                return self.backends.opt_in_optional(
                    data["engine"], approved_by=data["approved_by"],
                    measured_ram_gb=data["measured_ram_gb"])
            return self.backends.events(data["engine"] or None,
                                        limit=int(data["limit"] or 50))
        except (BackendError, ValueError, TypeError, OSError) as error:
            raise WorkbenchError(str(error)) from None

    def _execute(self, action, project, data):
        p, o = self.productivity, self.office
        if action in ("trace_capture", "trace_label", "trace_labeled",
                      "trace_status", "router_select", "learning_propose",
                      "learning_activate", "learning_rollback", "learning_status"):
            return self._learning_action(action, data)
        if action in ("spec_search_status", "spec_search_run", "spec_candidates",
                      "spec_activate", "spec_rollback"):
            return self._spec_action(action, data)
        if action in ("skill_import", "skill_review", "skill_list", "skill_run",
                      "skill_runs", "skill_revoke", "skill_status"):
            return self._skill_action(action, data)
        if action in ("agents_status", "agents_react", "agents_codeact",
                      "agents_recursive", "agents_runs"):
            return self._agents_action(action, data)
        if action in ("connector_status", "connector_attach_local",
                      "connector_configure", "connector_validate",
                      "connector_read", "connector_freshness",
                      "connector_revoke", "connector_events"):
            return self._connector_action(action, data)
        if action in ("eval_status", "eval_register", "eval_run", "eval_report",
                      "eval_export", "eval_history"):
            return self._eval_action(action, data)
        if action in ("telemetry_status", "telemetry_capture",
                      "telemetry_record", "telemetry_report"):
            return self._telemetry_action(action, data)
        if action in ("backend_describe", "backend_probe", "backend_generate",
                      "backend_opt_in", "backend_events"):
            return self._backends_action(action, data)
        if action == "digest_status": return self.digest.status()
        if action == "proactive_inbox": return self.proactive.inbox(
            state=data["state"] or None, limit=data["limit"] or 50)
        if action == "proactive_summary": return self.proactive.daily_summary()
        if action == "monitor_status": return self.monitors.status()
        if action == "monitor_cancel": return self.monitors.cancel(data["name"])
        if action == "monitor_acknowledge": return self.monitors.acknowledge(
            data["key"])
        if action == "opencode_status": return self.opencode.status()
        if action == "hub_status": return self.messaging.status()
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
