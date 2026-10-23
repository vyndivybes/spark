"""Capability 16 — Unified inference backends with honest engine states.

SPARK's existing transports (Ollama local HTTP, Gemini, Groq via
spark_intelligence Models) remain the real generation path; this layer adds
a uniform engine catalog around them:

* every engine is individually `not_configured`, `connected`,
  `model_not_installed`, `rate_limited` or `failed`; states are never
  inherited from another engine;
* local engines are probed without consent; cloud engines require explicit
  owner consent for both probe and generation and have no fallback;
* llama.cpp / vLLM / SGLang are optional lazy-loaded adapters: they stay
  `declared_not_active` until (a) the host shows the claimed hardware and
  (b) the owner explicitly opts in; nothing is downloaded;
* generation records measured latency and provider token counts through
  the capability-15 telemetry layer.
"""
from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import time
from pathlib import Path

IMPLEMENTED_ENGINES = {
    "ollama": {"transport": "local http /api/tags + /api/generate",
               "cloud": False},
    "gemini": {"transport": "cloud v1beta generateContent",
               "cloud": True},
    "groq": {"transport": "cloud chat/completions",
             "cloud": True},
}
OPTIONAL_ENGINES = ("llamacpp-local", "vllm-local", "sglang-local")
MIN_OPTIONAL_RAM_GB = 8.0
TOKENS_MAX = 10_000_000


class BackendError(ValueError):
    """Invalid backend configuration, probe or generation request."""


class InferenceBackends:
    def __init__(self, root, *, clock=time.time, hardware_ram_gb=None,
                 telemetry=None):
        self.root = Path(root) / "inference-backends"
        self.clock = clock
        # Measured host RAM (set by the workbench via psutil) or None when
        # unknown; optional engines stay refused until it is measured.
        self.hardware_ram_gb = hardware_ram_gb
        self.telemetry = telemetry
        self.probers = {}
        self.generators = {}
        self._optional_owners = {}
        if self.root.is_symlink():
            raise BackendError("Linked backend storage is prohibited.")

    @contextlib.contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "backends.sqlite3"
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS events("
                           "key TEXT PRIMARY KEY,engine TEXT,kind TEXT,"
                           "detail TEXT,latency_ms REAL,created REAL)")
            yield db
            db.commit()
        finally:
            db.close()

    def _event(self, engine, kind, detail, latency_ms=None):
        key = "b-" + str(int(self.clock() * 1_000_000)) + kind
        with self._db() as db:
            db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)",
                       (key, engine, kind, detail[:400], latency_ms,
                        self.clock()))
            db.execute("DELETE FROM events WHERE key NOT IN (SELECT key FROM "
                       "events ORDER BY created DESC LIMIT 300)")

    # -- adapter attachment (delegation, not duplication) ------------------
    def attach(self, engine, *, probe=None, generate=None):
        """Attach SPARK's real probe/generate callables for one engine."""
        if engine not in IMPLEMENTED_ENGINES:
            raise BackendError("Only implemented transports attach a probe: "
                               + str(engine))
        if probe is None and generate is None:
            raise BackendError("Attach a probe or a generate callable.")
        self.probers[engine] = probe or _no_probe
        self.generators[engine] = generate or _no_generate

    # -- measured probe ----------------------------------------------------
    def probe(self, engine, *, consented=False):
        info = IMPLEMENTED_ENGINES.get(engine)
        if info is None:
            return self._optional_state(engine)
        if not self.probers.get(engine) or self.probers[engine] is _no_probe:
            return {"engine": engine, "state": "not_configured",
                    "note": "no configured model for this engine on this host"}
        if info["cloud"] and consented is not True:
            raise BackendError("Cloud engine probe needs explicit owner consent.")
        started = time.perf_counter()
        try:
            status = self.probers[engine]()
        except Exception as error:
            latency = round((time.perf_counter() - started) * 1000)
            self._event(engine, "probe_failed", type(error).__name__, latency)
            return {"engine": engine, "state": "failed",
                    "reason": type(error).__name__,
                    "latency_ms": latency}
        latency = round((time.perf_counter() - started) * 1000)
        if not isinstance(status, dict) or "state" not in status:
            raise BackendError("Probe callable must return a state dict.")
        state = status["state"]
        if state not in ("connected", "model_not_installed", "unavailable",
                         "not_configured"):
            raise BackendError("Unknown probe state: " + str(state))
        self._event(engine, "probe_" + state, str(status.get("model", "")),
                    latency)
        return {**status, "engine": engine, "latency_ms": latency}

    def _optional_state(self, engine):
        if engine not in OPTIONAL_ENGINES:
            raise BackendError("Unknown engine: " + str(engine))
        owner = self._optional_owners.get(engine)
        if owner and self.hardware_ram_gb and \
                self.hardware_ram_gb >= MIN_OPTIONAL_RAM_GB:
            return {"engine": engine, "state": "opted_in_not_probed",
                    "note": "owner opted in; probe/generate adapters must be "
                            "attached before use"}
        return {"engine": engine, "state": "declared_not_active",
                "note": "optional lazy adapter; needs measured host RAM >= "
                        "%s GB and explicit owner opt-in; nothing is "
                        "downloaded" % MIN_OPTIONAL_RAM_GB}

    # -- measured generation ----------------------------------------------
    def generate(self, engine, prompt, *, consented=False):
        info = IMPLEMENTED_ENGINES.get(engine)
        if info is None:
            raise BackendError("Generation for this engine is impossible until "
                               "its optional adapter is implemented: "
                               + str(engine))
        if not self.generators.get(engine) or self.generators[engine] is _no_generate:
            raise BackendError("No configured model for this engine on this "
                               "host: " + engine)
        if info["cloud"] and consented is not True:
            raise BackendError("Cloud generation needs explicit owner consent.")
        if info["cloud"]:
            self._event(engine, "cloud_consent", "owner-approved generation")
        started = time.perf_counter()
        try:
            result = self.generators[engine](prompt)
        except Exception as error:
            latency = round((time.perf_counter() - started) * 1000)
            self._event(engine, "generate_failed", type(error).__name__, latency)
            if self.telemetry:
                self.telemetry.record(engine, latency_ms=latency,
                                      source="provider_report")
            raise BackendError("Generation failed: " + type(error).__name__) \
                from None
        if not isinstance(result, dict) or not isinstance(
                result.get("text"), str) or not result["text"].strip():
            raise BackendError("Generator must return a bounded text answer.")
        tokens = {}
        for key, label in (("input_tokens", "input"), ("output_tokens", "output")):
            value = result.get(key)
            if value is not None and (type(value) is not int or
                                      not 0 <= value <= TOKENS_MAX):
                raise BackendError("Provider token counts are integers in range.")
            if value is not None:
                tokens[label] = value
        latency_ms = round((time.perf_counter() - started) * 1000)
        self._event(engine, "generated", str(len(result["text"])), latency_ms)
        if self.telemetry and tokens.get("output") is not None:
            self.telemetry.record(
                engine, latency_ms=latency_ms,
                input_tokens=tokens.get("input"),
                output_tokens=tokens.get("output"),
                tokens_per_second=round(tokens["output"] / (latency_ms / 1000), 2)
                if latency_ms > 0 else None,
                source="provider_report")
        return {"engine": engine, "text": result["text"][:8000],
                "latency_ms": latency_ms,
                "tokens": {"input": tokens.get("input"),
                           "output": tokens.get("output")},
                "verified": False}

    # -- optional engine opt-in (hardware-checked, owner-only) -------------
    def opt_in_optional(self, engine, *, approved_by, measured_ram_gb):
        if engine not in OPTIONAL_ENGINES:
            raise BackendError("Not an optional engine: " + str(engine))
        if not approved_by or len(str(approved_by)) < 3:
            raise BackendError("Owner opt-in is required.")
        if type(measured_ram_gb) not in (int, float) or measured_ram_gb <= 0:
            raise BackendError("Provide a real measured RAM value.")
        if measured_ram_gb < MIN_OPTIONAL_RAM_GB:
            return {"engine": engine, "state": "declared_not_active",
                    "note": "measured RAM %s GB is below the %s GB floor"
                            % (measured_ram_gb, MIN_OPTIONAL_RAM_GB)}
        self._optional_owners[engine] = str(approved_by)[:60]
        self._event(engine, "opted_in", "by " + str(approved_by)[:60])
        return {"engine": engine, "state": "opted_in_not_probed",
                "note": "attach a working adapter before probing or generating"}

    # -- honest catalog ----------------------------------------------------
    def describe(self):
        engines = []
        for engine, info in IMPLEMENTED_ENGINES.items():
            attached = bool(self.probers.get(engine, _no_probe) is not _no_probe
                            or self.generators.get(engine, _no_generate)
                            is not _no_generate)
            engines.append({"engine": engine, "implemented": True,
                            "cloud": info["cloud"], "transport":
                            info["transport"],
                            "state": "configured_adapter_attached" if attached
                            else "not_configured"})
        for engine in OPTIONAL_ENGINES:
            engines.append(self._optional_state(engine))
        return {"engines": engines,
                "downloads": "refused (no automatic model downloads)",
                "fallback": "refused (no automatic cloud fallback)"}

    def events(self, engine=None, *, limit=50):
        with self._db() as db:
            if engine:
                rows = db.execute("SELECT * FROM events WHERE engine=? ORDER "
                                  "BY created DESC LIMIT ?",
                                  (engine, int(limit))).fetchall()
            else:
                rows = db.execute("SELECT * FROM events ORDER BY created DESC "
                                  "LIMIT ?", (int(limit),)).fetchall()
        return [dict(row) for row in rows]


def _no_probe():
    raise BackendError("No probe attached for this engine.")


def _no_generate(prompt):
    raise BackendError("No generator attached for this engine.")
