"""Minimal, non-executable source cards from Google Live grounding metadata.

Never treat source metadata as instructions or render Google's HTML snippets.
The browser receives only validated URLs and short human-readable titles.
"""
from urllib.parse import urlsplit

def extract_grounding_sources(metadata, limit=5):
    if not metadata:
        return []
    chunks=getattr(metadata,"grounding_chunks",None) or []
    out=[]
    seen=set()
    for chunk in chunks:
        web=getattr(chunk,"web",None)
        if not web:
            continue
        raw=getattr(web,"uri",None)
        if not isinstance(raw,str) or len(raw)>2048 or any(ord(x)<32 for x in raw):
            continue
        try:
            u=urlsplit(raw)
        except ValueError:
            continue
        if u.scheme not in ("https",) or not u.hostname or u.username or u.password:
            continue
        if raw in seen:
            continue
        title=getattr(web,"title",None)
        if not isinstance(title,str) or not title.strip():
            title=u.hostname
        title=" ".join(title.split())[:140]
        seen.add(raw)
        out.append({"title":title,"url":raw})
        if len(out)>=limit:
            break
    return out
