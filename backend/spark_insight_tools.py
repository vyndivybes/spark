"""Bounded read-only SPARK self-inspection tools for the voice conversation.

Every result distinguishes three cases explicitly, so the model can honestly
report what happened instead of guessing:

  status "ok"           the accessor ran and returned real evidence;
  status "unavailable"  the accessor itself failed (git missing, endpoint
                        down, file refused) - access, not content, is the issue;
  status "not_found"    the accessor worked but the requested source line /
                        file simply does not exist.

Safety bounds, unchanged by any argument:
  - git runs with a fixed read-only argv (no shell, no way to pass user text);
  - HTTP self-checks target loopback only, with a proxy-free opener and a
    short timeout;
  - the evolution-policy and release-store readers parse small JSON files and
    return selected fields only;
  - source search/read reuse the existing bounded helpers from
    spark_autonomous_engine and results are additionally capped.
"""
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

from spark_autonomous_engine import PROJECT_ROOT, read_source_file, search_source_code

GIT_REPORT_LIMIT = 50          # changed-file entries reported to the model
SEARCH_FILE_LIMIT = 15         # files returned per search
SEARCH_MATCH_LIMIT = 40        # total matching lines returned per search
HTTP_TIMEOUT = 6
SUBPROCESS_TIMEOUT = 10
RELEASE_MANIFEST_LIMIT = 5     # release manifests reported
JOURNAL_TAIL = 10              # journal events reported
MAX_POLICY_BYTES = 20000
MAX_JOURNAL_BYTES = 400000
BROKEN_POLICY = {"status": "unavailable",
                 "message": "Evolution policy is not initialized for this SPARK install."}

FALLBACK_RELEASE_STORES = (
    "%LOCALAPPDATA%\\SPARK\\workspace\\release-data",
    "D:\\SPARK-Evolution-Temp\\phase5\\release-data",
)


def _unavailable(message):
    return {"status": "unavailable", "message": message}


def _clip(text, limit=160):
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _run_git(*args):
    """Run one fixed, read-only git command. No argument ever comes from the model."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, _clip(f"git command failed: {error}")
    if completed.returncode != 0:
        return None, _clip(f"git exited {completed.returncode}: {completed.stderr}")
    return completed.stdout, None


def git_state():
    """Actual Git HEAD, branch and working-tree status of this SPARK checkout."""
    head, error = _run_git("rev-parse", "HEAD")
    if error is not None:
        return _unavailable(error)
    branch, error = _run_git("branch", "--show-current")
    if error is not None:
        return _unavailable(error)
    subject, error = _run_git("log", "-1", "--format=%h %s")
    if error is not None:
        return _unavailable(error)
    porcelain, error = _run_git("status", "--porcelain=v1", "-uall")
    if error is not None:
        return _unavailable(error)
    entries = [line.strip() for line in porcelain.splitlines() if line.strip()]
    staged = [entry for entry in entries if entry[:1] and entry[0] not in (" ", "?", "??")]
    return {
        "status": "ok",
        "head": head.strip(),
        "branch": branch.strip() or "(detached)",
        "last_commit": subject.strip(),
        "dirty": bool(entries),
        "changed_entries": len(entries),
        "staged_entries": len(staged),
        "clean_tree": len(entries) == 0,
        "sample_entries": entries[:GIT_REPORT_LIMIT],
    }


def _fetch_loopback(path):
    base = f"http://127.0.0.1:{os.environ.get('SPARK_BACKEND_PORT') or 8000}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base + path, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def backend_health():
    """Actual backend health, read from SPARK's own status endpoints."""
    payload = {"status": "ok", "backend": "unavailable", "channels": {}}
    try:
        report = _fetch_loopback("/status")
    except Exception as error:
        return _unavailable(_clip(f"backend status endpoint failed: {error}"))
    payload["backend"] = {
        "ai_provider": report.get("ai_provider"),
        "live_state": report.get("live_state"),
        "live_profile": report.get("live_profile"),
        "audio_transport": report.get("audio_transport"),
        "hands_free_ready": report.get("hands_free_ready"),
        "live_error_code": report.get("live_error_code"),
        "live_message": _clip(report.get("live_message", ""), 200),
    }
    for channel, endpoint in (("telegram", "/status/telegram"),
                              ("whatsapp", "/status/whatsapp")):
        try:
            channel_report = _fetch_loopback(endpoint)
        except Exception as error:
            payload["channels"][channel] = "unavailable"
            continue
        payload["channels"][channel] = {
            "state": channel_report.get("state"),
            "polling": channel_report.get("polling"),
        }
    return payload


def autonomy_policy():
    """Actual evolution-policy settings for this SPARK install."""
    localappdata = os.environ.get("LOCALAPPDATA")
    if not localappdata:
        return dict(BROKEN_POLICY)
    policy_path = Path(localappdata) / "SPARK" / "workspace" / "saee" / "autonomy-policy.json"
    try:
        raw = policy_path.read_text(encoding="utf-8")[:MAX_POLICY_BYTES]
    except FileNotFoundError:
        return dict(BROKEN_POLICY)
    except OSError as error:
        return _unavailable(_clip(f"policy unreadable: {error}"))
    try:
        policy = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return _unavailable("Evolution policy file is not valid JSON.")
    if not isinstance(policy, dict):
        return _unavailable("Evolution policy did not contain the expected settings.")
    return {
        "status": "ok",
        "policy_source": str(policy_path),
        "policy": {
            "enabled": policy.get("enabled"),
            "allow_model_source": policy.get("allow_model_source"),
            "max_upgrades_per_day": policy.get("max_upgrades_per_day"),
            "interval_seconds": policy.get("interval_seconds"),
            "last_status": policy.get("last_status"),
        },
    }


def _known_release_store():
    raw = os.environ.get("SPARK_RELEASE_STORE")
    priorities = [raw] if raw else FALLBACK_RELEASE_STORES
    for candidate in priorities:
        if not candidate:
            continue
        journal = Path(os.path.expandvars(candidate)) / "releases" / "journal.jsonl"
        if journal.is_file():
            return Path(os.path.expandvars(candidate))
    return None


def release_summary():
    """Recent controlled releases: manifests and journal tail from the release store."""
    store = _known_release_store()
    if store is None:
        return _unavailable("No SPARK release store is configured on this machine.")
    releases_dir = store / "releases"
    manifests = []
    try:
        folders = sorted(
            folder for folder in releases_dir.iterdir()
            if (folder / "manifest.json").is_file()
        )
    except OSError as error:
        return _unavailable(_clip(f"release store unreadable: {error}"))
    for folder in folders[-RELEASE_MANIFEST_LIMIT:]:
        try:
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifests.append({"release_id": folder.name, "manifest": "unreadable"})
            continue
        changes = manifest.get("changes") or []
        manifests.append({
            "release_id": manifest.get("release_id", folder.name),
            "release_status": manifest.get("status"),
            "files": [change.get("path") for change in changes],
            "candidate_sha256": [change.get("candidate_sha256") for change in changes],
            "validated_tests": manifest.get("validated_tests"),
        })
    journal_tail = []
    try:
        tail = (releases_dir / "journal.jsonl").read_text(
            encoding="utf-8", errors="replace")[-MAX_JOURNAL_BYTES:]
        lines = [line for line in tail.splitlines() if line.strip()]
        for line in lines[-JOURNAL_TAIL:]:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            journal_tail.append({
                "event": record.get("event"),
                "release_id": record.get("release_id"),
            })
    except OSError as error:
        journal_tail = [{"event": "journal_unreadable", "message": _clip(str(error))}]
    return {
        "status": "ok",
        "store": str(store),
        "recent_releases": manifests,
        "journal_tail": journal_tail,
    }


def search_spark_source(pattern):
    """Regex search over SPARK's bounded source scope, with results capped."""
    try:
        re.compile(pattern)
    except (re.error, TypeError) as error:
        return _unavailable(_clip(f"invalid search pattern: {error}"))
    results = {}
    total = 0
    truncated = False
    for rel_path, matches in search_source_code(pattern).items():
        if len(results) >= SEARCH_FILE_LIMIT:
            truncated = True
            break
        kept = matches[:SEARCH_MATCH_LIMIT - total]
        results[rel_path] = kept
        total += len(kept)
        if total >= SEARCH_MATCH_LIMIT:
            truncated = True
            break
    if not results:
        return {"status": "not_found",
                "message": "No source line matched this pattern.",
                "results": {}}
    return {
        "status": "ok",
        "results": results,
        "total_reported": total,
        "truncated": truncated,
    }


def read_spark_source_file(file_path, base="backend"):
    """Read a bounded portion of one SPARK source file via the existing helper."""
    content, error = read_source_file(str(file_path), base=base)
    if error is None:
        return {"status": "ok", "file_path": str(file_path), "content": content}
    if error.startswith("file not found:"):
        return {"status": "not_found",
                "message": _clip(error), "file_path": str(file_path)}
    return _unavailable(_clip(error))
