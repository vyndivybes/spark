import os
from pathlib import Path


class ObsidianIntegration:
    def __init__(self):
        self.vault = Path(os.path.expanduser(os.environ.get("SPARK_OBSIDIAN_VAULT", "~/Documents/Obsidian Vault")))

    def status(self):
        return {"enabled": self.vault.exists(), "vault": str(self.vault)}

    def search(self, query, limit=20):
        results = []
        if not self.vault.exists() or not query:
            return results
        ql = query.lower()
        for p in self.vault.rglob("*.md"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(self.vault))
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                if ql in rel.lower() or ql in text.lower():
                    results.append({"name": p.stem, "path": rel, "snippet": text[:240]})
                    if len(results) >= limit:
                        break
            except Exception:
                continue
        return results

    def read(self, path):
        target = (self.vault / path).resolve()
        vres = self.vault.resolve()
        if not str(target).startswith(str(vres)):
            raise ValueError("forbidden")
        if not target.exists() and not path.endswith(".md"):
            candidate = target.with_suffix(".md")
            if candidate.exists():
                target = candidate
        return target.read_text(encoding="utf-8", errors="ignore")


obsidian = ObsidianIntegration()
