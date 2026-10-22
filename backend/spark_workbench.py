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
from spark_opencode_agent import OpenCodeAgent, OpenCodeError
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
    "hub_status": set(),
    "hub_configure": {"channel", "config"},
    "hub_disconnect": {"channel"},
    "hub_approve": {"channel", "recipient", "text"},
    "hub_send": {"channel", "approval_id"},
    "hub_receive": {"channel"},
    "hub_history": {"limit"},
    "opencode_status": set(),
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
        self.messaging = MessagingHub(workspace.skills.root.parent)
        # The scoped OpenCode root is SPARK's own repository: sessions may
        # only work inside it, and every other path is refused.
        self.opencode = OpenCodeAgent(REPOSITORY_ROOT)
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
        if action in ("hub_configure", "hub_disconnect", "hub_approve", "hub_send",
                      "hub_receive", "hub_history"):
            return await self._hub(action, payload)
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
