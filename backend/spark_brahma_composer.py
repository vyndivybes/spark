"""Deterministic, read-only REA capability composition; never executes upstream code."""
from collections.abc import Mapping

# These are review leads, not claims of running features or permission to copy source.
FEATURES = (
    ("reflex_commands", "Brahma-sol", "PC autonomy", "allowlisted deterministic intent routing", 1, "medium"),
    ("memory_provenance", "Brahma-Echo", "ARKUS/Graphiti", "provenance, correction and expiry", 1, "medium"),
    ("browser_context", "Brahma-AI---Modular-Chrome-OS", "WEB_AGENT_VIEW", "least-privilege contextual actions", 1, "high"),
    ("android_pairing", "Brahma-Echo", "SPARK local transport", "authenticated encrypted device pairing", 1, "high"),
    ("voice_barge_in", "Brahma-sol", "SPARK voice", "benchmark optional local neural speech", 2, "medium"),
    ("self_recovery", "Brahma-Ai-Evo", "ARKUS Skill Forge", "isolated repairs and verified rollback", 2, "critical"),
    ("circuit_hud", "Brahma-Ai-Evo", "HOLO", "original wiring diagrams with voltage validation", 3, "high"),
    ("hologlobe", "Brahma-sol", "HOLO", "reuse existing 3D renderer", 3, "medium"),
)
LICENSE_STATUS = {
    "Brahma-sol": "conflict_review",  # README and LICENSE are inconsistent
    "Brahma-Ai-Evo": "private_only_no_distribution",
    "Brahma-AI---Modular-Chrome-OS": "mit_attribution",
    "Brahma-Echo": "source_available_restrictions",
}

def compose(*, confirmed_existing=None, license_overrides=None):
    """Return an evidence-aware proposal, never authority to import or execute code.

    Baseline booleans must come from independent SPARK testing. Missing evidence
    remains unverified, not 'absent'. Automatic license overrides are rejected.
    """
    if license_overrides is not None:
        raise ValueError("License decisions require independent human review.")
    if confirmed_existing is None:
        confirmed_existing = {}
    if not isinstance(confirmed_existing, Mapping):
        raise TypeError("confirmed_existing must be a mapping")
    known = {entry[0] for entry in FEATURES}
    if any(key not in known or type(value) is not bool
           for key, value in confirmed_existing.items()):
        raise ValueError("Unknown feature or non-boolean baseline evidence")
    rows = []
    for feature, source, existing, adaptation, priority, risk in FEATURES:
        baseline = confirmed_existing.get(feature)
        license_status = LICENSE_STATUS[source]
        rows.append({
            "feature": feature, "source": source, "existing_system": existing,
            "adaptation": adaptation, "priority": priority, "risk": risk,
            "baseline": "verified_existing" if baseline is True else
                        "verified_missing" if baseline is False else "unverified",
            "license": license_status,
            "reuse_policy": "limited_reuse_with_attribution" if license_status == "mit_attribution"
                            else "inspiration_only_until_review",
            "next_step": "do_not_duplicate" if baseline is True else "inspect_and_qualify",
            "execution_enabled": False, "tests_passed": False,
        })
    return {"schema_version": 1, "analysis_only": True,
            "source_count": len(LICENSE_STATUS), "candidates": rows}
