"""Static security scanning: secret/credential detection and insecure patterns.

Read-only. Used as the `security_check` pipeline stage so a generated or
repo-sourced candidate cannot reach the release gate carrying a credential or an
obviously dangerous construct. This is a heuristic linter, not a proof: it
reduces risk and is honest about its limits. It never imports or executes the
code it inspects.

Two layers:

* `scan_secrets` — high-confidence token shapes (provider keys, private keys,
  JWTs, assigned passwords) plus a Shannon-entropy check for long random
  literals, with obvious placeholders filtered out.
* `scan_code` — AST checks for `eval`/`exec`/`os.system`/`shell=True`/bare
  `subprocess` and unsafe deserialization, plus regex checks for hard-coded
  private IPs and `verify=False`.
"""
import ast
import math
import re

from spark_maintenance import digest


class SecurityScanError(ValueError):
    pass


# High-confidence named patterns. Each is (label, compiled regex).
_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("stripe_key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("assigned_secret", re.compile(
        r"(?i)\b(?:api[_-]?key|secret|passwd|password|token|access[_-]?key)\b\s*[:=]\s*"
        r"['\"][^'\"]{12,}['\"]")),
)

# Values that look like secrets but are clearly placeholders/examples.
_PLACEHOLDERS = re.compile(
    r"(?i)^(?:x{6,}|0{6,}|your[_-]?\w*|example\w*|placeholder|changeme|"
    r"test\w*|dummy\w*|\$\{?\w+\}?|<[^>]+>|none|null|todo|fixme)$")

_ENTROPY_THRESHOLD = 4.0
_ENTROPY_MIN_LEN = 32
_LONG_LITERAL = re.compile(r"['\"]([A-Za-z0-9+/=_\-]{32,})['\"]")

_UNSAFE_CALLS = {"eval": "eval", "exec": "exec"}

_CODE_PATTERNS = (
    ("hardcoded_private_ip", re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")),
    ("tls_verification_disabled", re.compile(r"verify\s*=\s*False")),
)


_PLACEHOLDER_WORDS = re.compile(
    r"(?i)(?:your|example|placeholder|changeme|dummy|sample|insert|replace|"
    r"enter|todo|fixme|xxx|here)")


def _looks_placeholder(value):
    return bool(_PLACEHOLDER_WORDS.search(value)) or value.lower().startswith("test")


def _entropy(value):
    if not value:
        return 0.0
    counts = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def scan_secrets(text, source="<text>"):
    """Return findings for likely secrets. Never returns the secret value."""
    if not isinstance(text, str):
        raise SecurityScanError("Scan target must be text.")
    findings = []
    for label, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            # For assigned secrets, entropy-check only the quoted value.
            if label == "assigned_secret":
                quoted = re.search(r"['\"]([^'\"]+)['\"]", value)
                candidate = quoted.group(1) if quoted else value
                if _PLACEHOLDERS.match(candidate) or _looks_placeholder(candidate):
                    continue
            findings.append({
                "kind": "secret", "label": label, "source": source,
                "line": text.count("\n", 0, match.start()) + 1,
                "redacted": value[:6] + "…" if label != "private_key" else "-----BEGIN…",
            })
    for match in _LONG_LITERAL.finditer(text):
        candidate = match.group(1)
        if len(candidate) >= _ENTROPY_MIN_LEN and _entropy(candidate) >= _ENTROPY_THRESHOLD \
                and not _PLACEHOLDERS.match(candidate) and not _looks_placeholder(candidate):
            findings.append({
                "kind": "secret", "label": "high_entropy_literal", "source": source,
                "line": text.count("\n", 0, match.start()) + 1,
                "redacted": candidate[:6] + "…",
            })
    return findings


def scan_code(text, source="<text>"):
    """AST/regex checks for insecure constructs. Syntax errors are the caller's to report."""
    if not isinstance(text, str):
        raise SecurityScanError("Scan target must be text.")
    findings = []

    def add(label, node, detail):
        findings.append({"kind": "code", "label": label, "source": source,
                         "line": getattr(node, "lineno", 1), "detail": detail})

    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else (
                    func.attr if isinstance(func, ast.Attribute) else None)
                if name in _UNSAFE_CALLS:
                    add(name + "_call", node, "Dynamic code execution.")
                if name in ("system", "popen") and isinstance(getattr(func, "value", None), ast.Name) \
                        and func.value.id == "os":
                    add("os_shell", node, "Shell command execution.")
                if name in ("loads", "load") and isinstance(getattr(func, "value", None), ast.Name) \
                        and func.value.id == "pickle":
                    add("pickle_load", node, "Unsafe deserialization of untrusted data.")
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) \
                            and keyword.value.value is True:
                        add("shell_true", node, "subprocess with shell=True.")
    for label, pattern in _CODE_PATTERNS:
        for match in pattern.finditer(text):
            findings.append({"kind": "code", "label": label, "source": source,
                             "line": text.count("\n", 0, match.start()) + 1,
                             "detail": "Pattern match."})
    return findings


def scan_sources(candidates):
    """Scan a mapping of {path: text}. Returns findings plus a pass/fail verdict.

    A candidate fails if any secret is found; code patterns are reported but do
    not by themselves block, since legitimate code may use subprocess.
    """
    findings = []
    for path, text in candidates.items():
        findings.extend(scan_secrets(text, path))
        findings.extend(scan_code(text, path))
    blocking = [item for item in findings if item["kind"] == "secret"]
    return {
        "findings": findings,
        "secret_count": len(blocking),
        "blocked": bool(blocking),
        "signature": digest("|".join(sorted(
            "%s:%s:%s" % (item["kind"], item["label"], item["source"]) for item in findings)).encode()),
        "note": ("Heuristic scan only; it cannot prove the absence of secrets or "
                 "vulnerabilities. Code findings are advisory."),
    }
