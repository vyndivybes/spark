"""Structured redacted tool-execution trace: fields, redaction, rotation.

The trace must answer acceptance questions — did a real tool run, was its
function response delivered back to Gemini — without ever storing secrets,
audio, conversation text, argument contents or source code.
"""
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import spark_tool_trace as trace  # noqa: E402


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.target = Path(tempfile.gettempdir()) / f"spark-trace-{uuid.uuid4().hex}.jsonl"
        self._real = trace._trace_path
        patcher = patch.object(trace, "_trace_path", lambda: self.target)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: self.target.unlink(missing_ok=True))

    def test_record_contains_required_fields(self):
        trace.record("tool_executed", route="gemini_live",
                     tool="get_spark_git_status", call_id="abc-1",
                     session="sess001", outcome="ok", detail="answer_len=120")
        record = json.loads(self.target.read_text(encoding="utf-8").splitlines()[-1])
        for field in ("ts", "event", "route", "tool", "call_id",
                      "session", "outcome", "detail"):
            self.assertIn(field, record)
        self.assertEqual(record["event"], "tool_executed")
        self.assertEqual(record["tool"], "get_spark_git_status")
        self.assertEqual(record["outcome"], "ok")
        self.assertIn("202", record["ts"][0:4])

    def test_long_values_are_bounded(self):
        trace.record("tool_executed", tool="x" * 500, call_id="y" * 500,
                     session="z" * 500, detail="d" * 500)
        record = json.loads(self.target.read_text(encoding="utf-8").splitlines()[-1])
        self.assertLessEqual(len(record["tool"]), 60)
        self.assertLessEqual(len(record["call_id"]), 40)
        self.assertLessEqual(len(record["session"]), 40)
        self.assertLessEqual(len(record["detail"]), 160)

    def test_content_cannot_leak_through_detail(self):
        secret = "AIzaSySuperSecretKeyMaterialValue0123456789"
        trace.record("tool_executed", tool="read_source_file",
                     call_id="c1", detail=secret)
        record = json.loads(self.target.read_text(encoding="utf-8").splitlines()[-1])
        self.assertNotIn(secret, record["detail"])
        self.assertLessEqual(len(record["detail"]), 160)

    def test_rotation_keeps_recent_records(self):
        # Fill the file above the rotation threshold, then record again.
        chunks = "\n".join(
            json.dumps({"ts": "t", "event": "noise", "tool": "x",
                        "detail": "pad" * 60}) for _ in range(40))
        self.target.write_text(chunks + "\n", encoding="utf-8")
        self.target.write_bytes(
            self.target.read_bytes() + (b"a" * 600_000) + b"\n")
        trace.record("tool_executed", tool="after_rotation", outcome="ok")
        raw = self.target.read_text(encoding="utf-8", errors="replace").splitlines()
        self.assertGreater(trace.TRACE_MAX_BYTES, self.target.stat().st_size,
                           "file rotated back under the size cap")
        last = json.loads(raw[-1])
        self.assertEqual(last["tool"], "after_rotation")
        self.assertLessEqual(len(raw), trace.TRACE_KEEP + 1)

    def test_read_tail_returns_dicts_and_survives_garbage(self):
        self.target.write_text("{bad json}\n", encoding="utf-8")
        trace.record("tool_executed", tool="t1", outcome="ok")
        records = trace.read_tail(limit=5)
        self.assertEqual(len(records), 1)
        self.assertIsInstance(records[0], dict)

    def test_record_never_raises_when_path_dirty(self):
        self.target.write_text("", encoding="utf-8")
        with patch.object(trace, "_trace_path", lambda: Path("Z:\\definitely-missing\\dir\\t.jsonl")):
            trace.record("tool_executed", tool="unwritable")  # must not raise


if __name__ == "__main__":
    unittest.main()
