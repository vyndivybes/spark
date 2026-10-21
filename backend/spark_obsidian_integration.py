import os
from pathlib import Path


class ObsidianIntegration:
    def __init__(self):
        self.vault = Path(os.path.expanduser(os.environ.get("SPARK_OBSIDIAN_VAULT", "~/Documents/Obsidian Vault")))

    def status(self):
        return {"enabled": self.vault.exists(), "vault": str(self.vault)}

    def snapshot(self):
        root=self.vault.resolve()
        if not root.is_dir(): raise ValueError('Configured vault unavailable.')
        notes=[];scanned=0
        for path in root.rglob('*.md'):
            scanned+=1
            if scanned>1000 or len(notes)>=100: break
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root): continue
            if path.stat().st_size>128_000: continue
            with path.open(encoding='utf-8',errors='replace') as stream: body=stream.read(4000)
            notes.append({'path':str(path.relative_to(root)),'name':path.stem,'text':body,'modified':path.stat().st_mtime})
        return {'ok':True,'source':'configured Obsidian vault','notes':notes,
                'limit':'Up to 100 notes; first 4,000 characters each; files up to 128 KB.','truncated':scanned>1000 or len(notes)>=100}

    def search(self, query, limit=20):
        results = []
        if not self.vault.exists() or not query:
            return results
        ql = query.lower()
        for p in self.vault.rglob("*.md"):
            if not p.is_file() or not p.resolve().is_relative_to(self.vault.resolve()):
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
        if not target.is_relative_to(vres):
            raise ValueError("forbidden")
        if not target.exists() and not path.endswith(".md"):
            candidate = target.with_suffix(".md")
            if candidate.exists():
                target = candidate
        return target.read_text(encoding="utf-8", errors="ignore")


obsidian = ObsidianIntegration()
