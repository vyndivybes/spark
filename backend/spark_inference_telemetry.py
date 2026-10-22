"""Capability 15 — Measured inference telemetry, no invented numbers.

Records only values that something actually measured and provided:

* latency comes from a wall-clock measurement around a real inference
  (the runner is injected, tests use a deterministic fake);
* tokens are provider-reported counts, bounded and validated;
* TTFT (time to first token) is only recorded when the engine produced a
  streamed measurement — otherwise it stays `not_measured`;
* host CPU/RAM deltas are computed from before/after samplers (psutil in
  production);
* energy (J or Wh) is refused unless a hardware power meter actually
  supplied it — there is never an estimated value;
* aggregates (per-model p50/p95 latency, tokens/second) and Markdown/JSON
  status reports are derived only from recorded measurements.
"""
from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import time
from pathlib import Path

TOKENS_MAX = 10_000_000
LATENCY_MAX_MS = 10 * 60 * 1000
KEEP_ENTRIES = 1000


class TelemetryError(ValueError):
    """Invalid or unmeasured telemetry input."""


class Telemetry:
    def __init__(self, root, *, clock=time.time, sampler=None):
        self.root = Path(root) / "inference-telemetry"
        self.clock = clock
        # sampler() returns {"cpu_percent": float, "ram_used_mb": float}
        self.sampler = sampler
        if self.root.is_symlink():
            raise TelemetryError("Linked telemetry storage is prohibited.")

    @contextlib.contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "telemetry.sqlite3"
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS entries("
                           "key TEXT PRIMARY KEY,model TEXT,latency_ms REAL,"
                           "input_tokens INTEGER,output_tokens INTEGER,"
                           "tokens_per_second REAL,ttft_ms TEXT,"
                           "cpu_delta_percent REAL,ram_delta_mb REAL,"
                           "energy TEXT,source TEXT,created REAL)")
            yield db
            db.commit()
        finally:
            db.close()

    # -- capture -----------------------------------------------------------
    def capture(self, model_id, runner, *, measure_again=None):
        """Measure a real inference call end to end (wall clock + vitals)."""
        if not re.fullmatch(r"[A-Za-z0-9_:.\-/]{1,80}", str(model_id)):
            raise TelemetryError("Model id is not a configured identifier.")
        if not callable(runner):
            raise TelemetryError("An inference runner callable is required.")
        before = self.sampler() if self.sampler else None
        started = time.perf_counter()
        try:
            answer = runner()
            if measure_again is not None:
                tokens = measure_again(answer)
            else:
                tokens = getattr(answer, "returned_usage", None)
        except TelemetryError:
            raise
        except Exception as error:
            raise TelemetryError("Inference failed; nothing measured: "
                                 + type(error).__name__) from None
        latency_ms = (time.perf_counter() - started) * 1000.0
        after = self.sampler() if self.sampler else None
        cpu_delta = ram_delta = None
        if before and after:
            cpu_delta = round(float(after.get("cpu_percent", 0)) -
                              float(before.get("cpu_percent", 0)), 2)
            ram_delta = round(float(after.get("ram_used_mb", 0)) -
                              float(before.get("ram_used_mb", 0)), 1)
        tokens = tokens or {}
        tps = None
        input_tokens = tokens.get("input")
        output_tokens = tokens.get("output")
        for value, name in ((input_tokens, "input"), (output_tokens, "output")):
            if value is not None and (type(value) is not int or
                                      not 0 <= value <= TOKENS_MAX):
                raise TelemetryError(name + " token count is provider-measured "
                                     "only (integer in range).")
        if output_tokens and latency_ms > 0:
            tps = round(output_tokens / (latency_ms / 1000.0), 2)
        return self.record(model_id, latency_ms=latency_ms,
                           cpu_delta_percent=cpu_delta, ram_delta_mb=ram_delta,
                           input_tokens=input_tokens,
                           output_tokens=output_tokens,
                           tokens_per_second=tps, source="measured_run")

    def record(self, model_id, *, latency_ms, input_tokens=None,
               output_tokens=None, tokens_per_second=None, ttft_ms=None,
               cpu_delta_percent=None, ram_delta_mb=None, energy=None,
               source="manually_recorded"):
        """Direct record; every field must be a measurement or stay None."""
        if not re.fullmatch(r"[A-Za-z0-9_:.\-/]{1,80}", str(model_id)):
            raise TelemetryError("Model id is not a configured identifier.")
        if type(latency_ms) not in (int, float) or not 0 <= latency_ms <= LATENCY_MAX_MS:
            raise TelemetryError("Latency must be a measured wall-clock value.")
        for value, name in ((input_tokens, "input tokens"),
                            (output_tokens, "output tokens")):
            if value is not None and (type(value) is not int or
                                      not 0 <= value <= TOKENS_MAX):
                raise TelemetryError(name + " must be provider-reported or None.")
        if tokens_per_second is not None and (type(tokens_per_second) not in
                                              (int, float) or
                                              tokens_per_second < 0):
            raise TelemetryError("tokens/second must be a measured rate.")
        ttft_text = "not_measured"
        if ttft_ms is not None:
            if type(ttft_ms) not in (int, float) or ttft_ms < 0:
                raise TelemetryError("TTFT must be a measured streamed value.")
            ttft_text = "%0.f" % ttft_ms
        if energy is not None:
            raise TelemetryError("Energy is not recorded: no measured power "
                                 "meter supplied; estimates are prohibited.")
        if source not in ("measured_run", "manually_recorded", "provider_report"):
            raise TelemetryError("Record the measurement source honestly.")
        key = "t-%s" % ("%015d" % int(self.clock() * 1_000_000))
        with self._db() as db:
            db.execute("INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (key, model_id, float(latency_ms), input_tokens,
                        output_tokens, tokens_per_second, ttft_text,
                        cpu_delta_percent, ram_delta_mb,
                        "not_measured", source, self.clock()))
            db.execute("DELETE FROM entries WHERE key NOT IN (SELECT key FROM "
                       "entries ORDER BY created DESC LIMIT ?)", (KEEP_ENTRIES,))
        return {"key": key, "recorded": True, "ttft": ttft_text,
                "energy": "not_measured"}

    # -- aggregates --------------------------------------------------------
    def aggregate(self, model_id=None):
        with self._db() as db:
            sql = ("SELECT model,COUNT(*) count,AVG(latency_ms) latency_mean,"
                   "AVG(tokens_per_second) tps_mean,"
                   "SUM(output_tokens) output_total "
                   "FROM entries")
            if model_id:
                rows = db.execute(sql + " WHERE model=? GROUP BY model",
                                  (model_id,)).fetchall()
            else:
                rows = db.execute(sql + " GROUP BY model").fetchall()
            latencies = {row["model"]: [entry["latency_ms"] for entry in
                                        db.execute(
                                            "SELECT latency_ms FROM entries "
                                            "WHERE model=? ORDER BY latency_ms",
                                            (row["model"],)).fetchall()]
                         for row in rows}
        aggregates = []
        for row in rows:
            samples = latencies[row["model"]]
            aggregates.append({
                "model": row["model"], "count": row["count"],
                "latency_p50_ms": round(samples[len(samples) // 2], 1) if samples else None,
                "latency_p95_ms": round(samples[int(len(samples) * 0.95)], 1)
                if samples else None,
                "latency_mean_ms": round(row["latency_mean"] or 0, 1),
                "tokens_per_second_mean": round(row["tps_mean"], 2)
                if row["tps_mean"] is not None else None,
                "output_tokens_total": row["output_total"] or 0})
        return aggregates

    def report(self, model_id=None):
        """Markdown telemetry report with measured-only provenance."""
        aggregates = self.aggregate(model_id)
        lines = ["# Inference telemetry report", "",
                 "Provenance: measured wall-clock + provider-reported tokens "
                 "only. TTFT requires streaming; energy requires a power "
                 "meter. No estimates are recorded."]
        if not aggregates:
            lines.append("No measurements recorded yet.")
        for row in aggregates:
            lines += ["",
                      "## %s" % row["model"],
                      "- runs recorded: %d" % row["count"],
                      "- latency p50/p95/mean ms: %s / %s / %s" % (
                          row["latency_p50_ms"], row["latency_p95_ms"],
                          row["latency_mean_ms"]),
                      "- tokens/second mean: %s" % row["tokens_per_second_mean"],
                      "- output tokens total: %d" % row["output_tokens_total"]]
        return "\n".join(lines)

    def status(self):
        with self._db() as db:
            count = db.execute("SELECT COUNT(*) count FROM entries"
                               ).fetchone()["count"]
        return {"entries": count,
                "ttft": "recorded only for streamed measurements",
                "energy": "not_measured (no hardware meter; estimates refused)",
                "sampler": "injected (psutil-backed in production)"}
