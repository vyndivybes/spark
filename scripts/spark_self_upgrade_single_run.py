"""One authenticated SAEE isolated-upgrade run through SPARK's own engine.

Drives the actual evolution engine exactly as server.py wires it
(Evolution(SparkWorkspace(_SPARK_WORKSPACE_ROOT))), queues one narrowly
scoped goal, runs ONE run_once cycle (REA catalog discovery only, isolated
D: generation/validation, engine-owned promotion gates) and immediately
emergency-stops recurring autonomy. Nothing in the live work tree is
written by this script; a dirty work tree keeps any candidate in isolation
by design. Never prints keys; the only network inference is SPARK's own
free-tier Groq adapter with no paid fallback by construction.
"""
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

SPARK_WORKSPACE = Path(
    os.environ.get("SPARK_WORKSPACE_DATA_ROOT")
    or (Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".spark")
        / "SPARK" / "workspace"))

OUT = Path(os.environ.get('SPARK_SELF_UPGRADE_OUT') or
           (r"D:\SPARK-Evolution-Temp\self-upgrade-test\engine-out-" + time.strftime('%Y%m%d-%H%M%S')))
TARGET_REL = "backend/spark_insight_tools.py"
GOAL = (
    "Fix only backend/spark_insight_tools.py read_spark_source_file. After file-not-found, "
    "REMOVE one leading matching base segment using either separator before retry. "
    "Never prepend base: read_source_file already joins it. For backend/example.py or "
    "backend BACKSLASH example.py with base=backend, retry example.py; likewise src paths "
    "with base=src. Preserve initial success, original file_path, refusal/traversal checks, "
    "unavailable and missing errors. Acceptance: all tests/test_spark_insight_tools_paths.py "
    "cases. One file; do not change tests."
)


def git_dirty():
    import subprocess
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                          capture_output=True, text=True, timeout=15)
    status = subprocess.run(["git", "status", "--porcelain=v1", "-uall"], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=15)
    entries = [line for line in status.stdout.splitlines() if line.strip()]
    return {"head": head.stdout.strip(),
            "dirty": bool(entries),
            "entry_count": len(entries),
            "first_entries": entries[:12]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    target = ROOT / TARGET_REL
    summary = {
        "started": time.time(),
        "goal": GOAL,
        "target": TARGET_REL,
        "target_sha256_before": None,
        "policy_before": None,
        "policy_after": None,
        "autonomy_status_after": None,
        "git_state": git_dirty(),
        "run_result": None,
        "artifacts": {},
        "groq_adapter_contract": {
            "adapter": "spark_evolution.generate_json -> Spark GroqClient chat/completions",
            "model": os.environ.get("SPARK_GROQ_MODEL") or "openai/gpt-oss-20b",
            "temperature": 0,
            "request_budget_bytes": 10000,
            "output_budget_tokens": 2048,
            "free_tier_enforcement": "HTTP 429 -> 'free-tier rate limit reached; "
                                     "no automatic retry or paid fallback.'",
            "cost_verified": "free-tier only; SPARK's adapter has no paid "
                             "fallback or billing path by construction",
        },
    }
    import hashlib
    summary["target_sha256_before"] = hashlib.sha256(target.read_bytes()).hexdigest()
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=BACKEND / ".env")  # SPARK's own credential mechanism.
    from spark_workspace import SparkWorkspace
    from spark_evolution import Evolution
    from spark_groq import GroqClient

    # Observe the real transport without substituting its inputs or response.
    # Retain only bounded metadata, never authorization headers or source text.
    invocations = []
    original_http = GroqClient._http

    async def observed_http(client, url, **kwargs):
        body = kwargs.get('body') or {}
        event = {'started': time.time(), 'model': body.get('model'),
                 'request_bytes': len(json.dumps(body.get('messages', []), ensure_ascii=False).encode()),
                 'max_completion_tokens': body.get('max_completion_tokens'),
                 'request_sha256': hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()}
        invocations.append(event)
        try:
            response = await original_http(client, url, **kwargs)
            event.update(finish_reason=response['choices'][0].get('finish_reason'),
                         usage=response.get('usage'),
                         response_sha256=hashlib.sha256(json.dumps(response, sort_keys=True).encode()).hexdigest(),
                         outcome='returned')
            return response
        except Exception as error:
            event.update(outcome='failed', exception_type=type(error).__name__)
            raise
        finally:
            event['finished'] = time.time()
            (OUT / 'model-invocations.json').write_text(json.dumps(invocations, indent=2), encoding='utf-8')

    GroqClient._http = observed_http

    policy_path = SPARK_WORKSPACE / "saee" / "autonomy-policy.json"
    if policy_path.is_file():
        summary["policy_before"] = json.loads(policy_path.read_text(encoding="utf-8"))

    engine = Evolution(SparkWorkspace(SPARK_WORKSPACE))
    autonomy = engine.autonomy
    try:
        # The engine's own cooldown governs single cycles; wait it out
        # instead of touching the recorded state.
        pre = autonomy.status()
        pending = float(pre.get("last_cycle", 0)) + int(
            pre.get("interval_seconds", 300)) - time.time()
        if pending > 400:
            raise RuntimeError('Engine cooldown exceeds the single-run wait budget.')
        if pending > 0:
            print('Waiting for the existing engine cooldown before the single cycle.', flush=True)
            deadline = time.monotonic() + pending + 1
            while time.monotonic() < deadline:
                time.sleep(min(30, deadline - time.monotonic()))
            summary['cooldown_waited_seconds'] = round(pending + 1)
        configure_status = autonomy.configure(enabled=True, allow_model_source=True)
        summary["policy_after_configure"] = {
            "enabled": configure_status["enabled"],
            "allow_model_source": configure_status["allow_model_source"]}
        try:
            autonomy.cancel_goal()  # discard any goal left queued by a prior run
        except Exception:
            pass
        autonomy.queue_goal(GOAL)
        result = asyncio.run(autonomy.run_once("general"))
        summary["run_result"] = result
    except Exception as error:
        summary['run_result'] = {'status': 'runner_failed', 'exception_type': type(error).__name__,
                                 'reason': str(error)[:200]}
    finally:
        GroqClient._http = original_http
        summary['model_invocations'] = invocations
        try:
            autonomy.emergency_stop()
            summary["autonomy_status_after"] = {
                "enabled": autonomy.state.get("enabled"),
                "allow_model_source": autonomy.state.get("allow_model_source"),
                "last_status": autonomy.state.get("last_status")}
        except Exception as error:  # never leave the grant open
            summary["autonomy_status_after"] = {"emergency_stop_error":
                                                str(error)[:160]}
        if policy_path.is_file():
            summary["policy_after"] = json.loads(policy_path.read_text(encoding="utf-8"))

    # artifacts: the isolated workspace the engine produced
    run_result = summary.get("run_result") or {}
    workspace_name = run_result.get("workspace")
    if not workspace_name and run_result.get('candidate_id'):
        record = autonomy.isolated.candidate_record(run_result['candidate_id'])
        workspace_name = record.get('workspace') if record else None
    if workspace_name:
        isolated_base = Path(os.environ.get("SPARK_ISOLATED_ROOT")
                             or r"D:\SPARK-Evolution-Temp\isolated-upgrades")
        ws = isolated_base / workspace_name
        if ws.is_dir():
            dest = OUT / ("workspace-" + workspace_name)
            shutil.copytree(ws, dest)
            record = ws / "candidate.json"
            if record.is_file():
                try:
                    summary["candidate_record"] = json.loads(
                        record.read_text(encoding="utf-8"))
                except ValueError:
                    pass
    # engine analysis records (redacted: bounded excerpts, no keys)
    analyses = SPARK_WORKSPACE / "repository-analyses" / "general"
    if analyses.is_dir():
        fresh = [p for p in sorted(analyses.glob("*.json"),
                                   key=lambda p: p.stat().st_mtime)
                 if p.stat().st_mtime >= summary["started"]]
        for record in fresh:
            dest = OUT / record.name
            shutil.copyfile(record, dest)
            summary["artifacts"]["analysis_record"] = str(dest)
    # isolated-runner audit tail
    audit = Path(os.environ.get("SPARK_ISOLATED_ROOT")
                 or r"D:\SPARK-Evolution-Temp\isolated-upgrades") / "audit.jsonl"
    if audit.is_file():
        tail = audit.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
        (OUT / "isolated-audit-tail.jsonl").write_text("\n".join(tail) + "\n",
                                                       encoding="utf-8")
        summary["artifacts"]["isolated_audit_tail"] = str(OUT / "isolated-audit-tail.jsonl")

    summary["finished"] = time.time()
    summary['target_sha256_after'] = hashlib.sha256(target.read_bytes()).hexdigest()
    out_file = OUT / "single-run-summary.json"
    out_file.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    compact = {key: summary.get(key) for key in
               ("run_result", "policy_after", "autonomy_status_after",
                "status_sequence")}
    print(json.dumps(compact, indent=1, default=str))
    return 0 if run_result.get('status') in {'isolated_staged', 'applied', 'isolated_ready'} else 1


if __name__ == "__main__":
    raise SystemExit(main())
