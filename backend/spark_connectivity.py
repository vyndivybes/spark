"""A10 system connectivity classification for the configured SPARK host.

Read-only evidence rules: host SPARK_MCP_SERVERS registration, recent audit
history, credential presence and local install markers. No secrets are echoed
and no external calls happen unless the caller asks for probes.
"""
import asyncio
import os
import shutil
import time
from pathlib import Path

from spark_integrations import Integrations

STATES = ("verified operational", "partially operational",
          "installed but disconnected", "not installed", "failed verification",
          "unknown")

SERVER_DISPLAY = {
    "vaos": "VAOS", "vyndi-os": "VYNDI OS", "vedm": "VEDM",
    "vaos-jarvis": "VAOS Jarvis", "gmail": "Gmail", "google-drive": "Google Drive",
    "google-calendar": "Google Calendar", "github": "GitHub", "slack": "Slack",
    "graphify": "Graphify", "graphiti": "Graphiti", "hermes": "Hermes",
}

AUDIT_WINDOW_SECONDS = 7 * 86400

PROBE_SKIP = ("vaos-jarvis",)


def default_audit_dir():
    root = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".spark")
    return Path(root) / "SPARK" / "workspace" / "integrations"


class ConnectivityError(ValueError):
    pass


class Connectivity:
    def __init__(self, *, root=None, integrations=None, env=None, exists=None,
                 which=None, clock=time.time, homedir=None):
        self.root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
        self.integrations = integrations
        self.env = dict(os.environ) if env is None else dict(env)
        self.exists = (lambda target: Path(target).exists()) if exists is None else exists
        self.which = shutil.which if which is None else which
        self.clock = clock
        self.home = str(Path(homedir) if homedir else Path.home())

    def _key(self, name):
        return self.env.get(name, "").strip()

    def _catalog(self):
        if self.integrations is None:
            self.integrations = Integrations(audit_dir=default_audit_dir())
        try:
            config = self.integrations.catalog()
        except Exception:
            return None
        return config if isinstance(config, dict) else None

    def _recent_ok(self, servers):
        servers = set(servers)
        if not servers:
            return {}
        try:
            history = self.integrations.history()
        except Exception:
            return {}
        now = self.clock()
        evidence = {}
        if not isinstance(history, list):
            return {}
        for record in history:
            if not isinstance(record, dict) or record.get("ok") is not True:
                continue
            name = record.get("server")
            stamp = record.get("at")
            if name in servers and isinstance(stamp, (int, float)) and now - stamp <= AUDIT_WINDOW_SECONDS:
                evidence[name] = stamp
        return evidence

    def _entry(self, name, state, evidence, *, server=None):
        if state is not None and state not in STATES:
            raise ConnectivityError(f"Refusing an unknown state label: {state!r}")
        entry = {"name": name, "state": state, "evidence": evidence}
        if server is not None:
            entry["server"] = server
        return entry

    def _registered(self, display, server, evidence, audited):
        if server in audited:
            return self._entry(display, "partially operational",
                               evidence + " Successful audited call recorded within the last 7 days.",
                               server=server)
        return self._entry(display, "installed but disconnected",
                           evidence + (" No successful audited call in the last 7 days; "
                                       "run the probed report to verify."), server=server)

    def _obsidian_vault(self):
        return self.env.get("SPARK_OBSIDIAN_VAULT") or os.path.join(
            self.home, "Documents", "Obsidian Vault")

    def _static_entries(self):
        config = self._catalog()
        names = set(config) if config else set()
        # Jarvis uses Electron's isolated session instead of a stdio registry
        # entry. A configured bridge still needs a signed-in founder session.
        jarvis = getattr(self.integrations, 'jarvis', None)
        if config is not None and jarvis is not None and jarvis.configured():
            names.add('vaos-jarvis')
        business=getattr(self.integrations,'business',None)
        if config is not None and business is not None and business.configured():
            names.update(('vyndi-os','vedm'))
        audited = self._recent_ok(names)
        by_name = {}

        if config is None:
            by_name["MCP registration"] = self._entry(
                "MCP registration", "unknown",
                "The host SPARK_MCP_SERVERS value failed validation; no service can register.")
            by_name["VAOS"] = self._entry("VAOS", "unknown",
                                          "Registration is invalid; connectivity cannot be assessed.")
            for display in ("VYNDI OS", "VEDM", "VAOS Jarvis", "GitHub", "Google Drive",
                            "Gmail", "Google Calendar", "Slack", "Graphify", "Graphiti",
                            "Hermes"):
                by_name[display] = self._entry(display, "unknown", "Registration is invalid.")
        else:
            for server in ("vaos", "vyndi-os", "vedm", "vaos-jarvis", "gmail",
                           "google-drive", "google-calendar", "github", "slack"):
                display = SERVER_DISPLAY[server]
                if server in names:
                    evidence = "Registered under SPARK_MCP_SERVERS."
                    if server == "vaos-jarvis":
                        evidence = ("Session-managed advisory; each question verifies the "
                                    "VAOS founder session from this authorized client.")
                    if server in ('vyndi-os','vedm') and server not in config:
                        evidence=('Electron session read of a seeded authority reference; not a live ledger.'
                                  if server=='vyndi-os' else
                                  'Published engineering-library reference read; not synchronization or release approval.')
                    by_name[display] = self._registered(display, server, evidence, audited)
                else:
                    by_name[display] = self._entry(
                        display, "not installed",
                        "No authorized MCP endpoint is configured under this name. "
                        "SPARK never assumes endpoints or credentials.")

            graphify_exe = self.root / ".venv" / "Scripts" / "graphify-mcp.exe"
            if "graphify" in names:
                by_name["Graphify"] = self._registered(
                    "Graphify", "graphify",
                    "Registered under SPARK_MCP_SERVERS (start-spark registers it when "
                    ".venv\\Scripts\\graphify-mcp.exe exists).", audited)
            elif self.exists(graphify_exe) and self.exists(self.root / "graphify-out" / "graph.json"):
                by_name["Graphify"] = self._entry(
                    "Graphify", "installed but disconnected",
                    "graphify-mcp.exe and the architecture graph exist locally, but the "
                    "server is not registered under SPARK_MCP_SERVERS.")
            else:
                by_name["Graphify"] = self._entry(
                    "Graphify", "not installed",
                    "No graphify-mcp.exe install and no registration found.")

            if "graphiti" in names:
                missing = "Credentials for fact extraction or embeddings are missing." if not (
                    self._key("GROQ_API_KEY") and self._key("GEMINI_API_KEY")) else \
                    "Credentials for fact extraction and embeddings are present."
                by_name["Graphiti"] = self._registered(
                    "Graphiti", "graphiti", "Registered under SPARK_MCP_SERVERS. " + missing, audited)
            elif self.exists(self.root / ".venv-graphiti"):
                by_name["Graphiti"] = self._entry(
                    "Graphiti", "installed but disconnected",
                    "Its virtual environment exists; register it with start-spark "
                    "-EnableGraphiti to connect.")
            else:
                by_name["Graphiti"] = self._entry(
                    "Graphiti", "not installed",
                    "No optional Graphiti environment and no registration found.")

            if "hermes" in names:
                by_name["Hermes"] = self._registered(
                    "Hermes", "hermes",
                    "Registered under SPARK_MCP_SERVERS as a read-only learned-experience "
                    "sidecar.", audited)
            elif self.exists(self.root / ".venv-hermes"):
                by_name["Hermes"] = self._entry(
                    "Hermes", "installed but disconnected",
                    "Its virtual environment exists; register it with start-spark "
                    "-EnableHermes to connect.")
            else:
                by_name["Hermes"] = self._entry(
                    "Hermes", "not installed",
                    "No optional Hermes environment and no registration found.")

        command = self._key("SPARK_REA_COMMAND")
        if command:
            by_name["REA"] = self._entry(
                "REA", "installed but disconnected",
                "SPARK_REA_COMMAND is configured; the catalog loads when a session calls "
                "REA tools, outside this MCP registration. Live probing is left to the "
                "REA tools screen.")
        elif self.which("npx"):
            by_name["REA"] = self._entry(
                "REA", "installed but disconnected",
                "No SPARK_REA_COMMAND; the default npx route is available on PATH. The "
                "catalog loads only when a session calls REA tools, outside this MCP "
                "registration. Live probing is left to the REA tools screen.")
        else:
            by_name["REA"] = self._entry(
                "REA", "not installed",
                "No REA command, default npx route or registration is available.")

        if "Obsidian" not in by_name:
            vault = self._obsidian_vault()
            if self.exists(vault):
                by_name["Obsidian"] = self._entry(
                    "Obsidian", "partially operational",
                    f"Vault present at the configured location. Searches verify themselves "
                    f"when invoked.")
            else:
                by_name["Obsidian"] = self._entry(
                    "Obsidian", "not installed",
                    f"No vault at {vault} and no environment override.")

        groq_key = self._key("GROQ_API_KEY")
        gemini_key = self._key("GEMINI_API_KEY")
        by_name["LLM providers"] = self._entry(
            "LLM providers",
            "partially operational" if (groq_key or gemini_key) else "not installed",
            ("Groq and Gemini keys control text and multimodal generation. "
             f"Groq: {'configured' if groq_key else 'missing'}; "
             f"Gemini: {'configured' if gemini_key else 'missing'}. "
             "Credentials are never echoed; no API call is made from this report."))
        by_name["Voice and multimodal services"] = self._entry(
            "Voice and multimodal services",
            "partially operational" if (groq_key or gemini_key) else "installed but disconnected",
            ("Local hands-free audio runs in the authorized session. Cloud voice needs "
             f"Groq ({'configured' if groq_key else 'missing'}) and Gemini "
                 f"({'configured' if gemini_key else 'missing'}). Live session state belongs "
     "to runtime diagnostics, not this static report."))

        order = []
        base = ("MCP registration", "Graphify", "Graphiti", "Hermes", "REA", "Obsidian",
                "VAOS", "VYNDI OS", "VEDM", "VAOS Jarvis", "GitHub", "Google Drive",
                "Gmail", "Google Calendar", "Slack", "LLM providers",
                "Voice and multimodal services")
        for display in base:
            if display in by_name:
                order.append(display)
        for display, entry in by_name.items():
            if display not in order:
                order.append(display)
        return [by_name[display] for display in order]

    async def _probe(self, entry):
        server = entry["server"]
        try:
            result = await self.integrations.execute(server, "mcp_discover", {})
            tools = len(result) if isinstance(result, list) else 0
            if server in ('vyndi-os','vedm') and server not in self.integrations.catalog() and getattr(self.integrations,'business',None) is not None and self.integrations.business.configured():
                from spark_business import BUSINESS_TOOLS
                read=await self.integrations.execute(server,'mcp_call',{'name':BUSINESS_TOOLS[server]['name'],'arguments':{}})
                if read.get('isError'):
                    raise ConnectivityError('Reference read failed. Check portal sign-in and source availability.')
                entry['evidence'] += ' Actual reference read succeeded; source limitations still apply.'
            entry["state"] = "verified operational"
            entry["probe"] = {"ok": True, "tools": tools}
            entry["evidence"] = entry["evidence"] + " Live discovery succeeded."
        except Exception as error:
            entry["state"] = "failed verification"
            entry["probe"] = {"ok": False, "error": str(error)[:200]}
            entry["evidence"] = entry["evidence"] + " Live discovery failed."

    async def report(self, *, deep=False):
        entries = await asyncio.to_thread(self._static_entries)
        probed = 0
        if deep:
            if self.integrations is None:
                self.integrations = Integrations(audit_dir=default_audit_dir())
            for entry in entries:
                server = entry.get("server")
                if not server or server in PROBE_SKIP:
                    continue
                probed += 1
                await self._probe(entry)
        return {
            "entries": entries,
            "deep": bool(deep),
            "probed": probed,
            "note": ("Round-trip probe of each registered MCP service. A successful "
                     "discovery verifies the connection; failures keep everything "
                     "read-only and the circuit breaker protects retries."
                     if deep else
                     "Static classification only: registration, audit history, install "
                     "markers and credential presence. Run the probed report for live "
                     "verification of configured MCP services."),
        }


