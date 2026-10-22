"""Source-only OpenJarvis capability inventory for SPARK.

This is an *audit utility*, not a service health checker. A source file's
presence never means an integration works, or that user data can be read.
No credentials, network connections, subprocesses or optional packages.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final


@dataclass(frozen=True)
class Feature:
    number: int
    slug: str
    name: str
    foundation_paths: tuple[str, ...]
    live_acceptance: str
    priority: str


FEATURES: Final[tuple[Feature, ...]] = (
    Feature(1, "morning_digest", "Complete Morning Digest",
            ("backend/spark_google_mcp.py", "backend/spark_sync.py",
             "backend/spark_morning_digest.py"),
            "Live authenticated source reads, digest history, execution and notification evidence", "P1"),
    Feature(2, "whatsapp", "WhatsApp messaging",
            ("backend/spark_integrations.py", "backend/spark_messaging_hub.py"),
            "Authenticated two-way message, allowed sender, outbound consent and receipt", "P1"),
    Feature(3, "proactive_agent", "Proactive agent",
            ("backend/spark_task_engine.py", "backend/spark_workforce.py"),
            "Persisted proposed actions, exact approval, execution and follow-up", "P1"),
    Feature(4, "opencode", "Native OpenCode agent",
            ("backend/spark_repo_upgrade.py", "backend/spark_autonomous_engine.py",
             "backend/spark_opencode_agent.py"),
            "Real OpenCode session, diff review, bounded test and explicit merge gate", "P1"),
    Feature(5, "deep_research", "Multi-hop deep research",
            ("backend/spark_intelligence/memory.py", "backend/spark_grounding.py"),
            "Several actual retrieval hops with grounded citations and bounded budget", "P1"),
    Feature(6, "messaging_hub", "Multi-channel messaging hub",
            ("backend/spark_slack_mcp.py", "backend/spark_integrations.py",
             "backend/spark_messaging_hub.py"),
            "Authenticated inbound and outbound messages through tested channel adapters", "P1"),
    Feature(7, "trace_learning", "Trace-driven learning",
            ("backend/spark_intelligence/policy.py",),
            "Measured real outcomes improve a held-out benchmark without regression", "P2"),
    Feature(8, "spec_search", "LLM-guided specification search",
            ("backend/spark_evolution.py", "backend/spark_auto_evolution.py"),
            "Diagnose/plan/test/gate/record with independent rollback and approval", "P2"),
    Feature(9, "skills", "Skill ecosystem",
            ("backend/spark_intelligence/skills.py", "backend/arkus_skill_forge.py"),
            "Reviewed external skill import, bounded pipeline invocation and rollback", "P2"),
    Feature(10, "advanced_agents", "Advanced agent runtimes",
            ("backend/spark_intelligence/service.py",),
            "ReAct, CodeAct and recursive adapters pass safe scenario tests", "P2"),
    Feature(11, "continuous_monitors", "Long-running monitor agents",
            ("backend/spark_intelligence/runtime.py", "backend/spark_sync.py"),
            "Persisted monitoring survives restart, deduplicates and emits real notifications", "P2"),
    Feature(12, "adaptive_routing", "Adaptive model routing",
            ("backend/spark_intelligence/models.py", "backend/spark_intelligence/policy.py"),
            "Measured trace-adapted routing wins a held-out benchmark within constraints", "P2"),
    Feature(13, "connector_catalog", "Broad data connector catalog",
            ("backend/spark_integrations.py", "backend/spark_google_mcp.py"),
            "Every enabled source validates its own account, actual read, freshness and revoke", "P3"),
    Feature(14, "evaluations", "Standardized evaluations",
            ("backend/spark_profiler.py", "tests/test_spark_intelligence_runtime.py"),
            "Reproducible scoring on labeled unseen dataset with report export", "P3"),
    Feature(15, "telemetry", "Inference telemetry and efficiency",
            ("backend/spark_profiler.py", "backend/spark_host_vitals.py"),
            "Actual latency, TTFT and tokens; energy only where measured", "P3"),
    Feature(16, "inference_backends", "Unified inference backends",
            ("backend/spark_intelligence/models.py", "backend/spark_groq.py"),
            "Configured local backend health and real generation for each supported engine", "P3"),
)


def _checked_file(root: Path, relative: str) -> bool:
    """Allow only ordinary files inside the selected repository root."""
    candidate = root.joinpath(*relative.split("/"))
    if candidate.is_symlink() or not candidate.is_file():
        return False
    try:
        candidate.resolve(strict=True).relative_to(root)
    except (OSError, ValueError, RuntimeError):
        return False
    return True


def inventory(repo_root: str | Path) -> dict:
    """Report evidence of code *foundations*, never live feature completion.

    No network or execution is attempted; all features remain unverified.
    The output is designed to feed an independent acceptance runner later.
    """
    root = Path(repo_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Repository root must be a directory")
    if not (root / "backend").is_dir():
        raise ValueError("Repository root must contain a backend directory")
    features = []
    for f in FEATURES:
        paths = tuple(p for p in f.foundation_paths if _checked_file(root, p))
        features.append({
            "id": f.number, "slug": f.slug, "name": f.name, "priority": f.priority,
            "foundation_files_present": list(paths),
            "foundation_files_expected": list(f.foundation_paths),
            "source_status": "FOUNDATION_PRESENT" if paths else "NO_FOUNDATION_FOUND",
            "live_status": "UNVERIFIED",
            "acceptance_requirement": f.live_acceptance,
        })
    return {
        "schema": "spark.openjarvis16.readiness.v1",
        "count": len(features),
        "verified_live_count": 0,
        "note": "Source inspection only. A found file is not proof of implementation, connectivity or live acceptance.",
        "features": features,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only source audit for SPARK/OpenJarvis 16-feature rollout")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = inventory(args.root)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
