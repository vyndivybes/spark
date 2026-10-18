"""Deterministic local-only speech search for SPARK's project knowledge."""
import re

def knowledge_search_query(utterance):
    if not isinstance(utterance,str) or len(utterance)>220:
        return None
    utterance=re.sub(r"\s+"," ",utterance.strip()).rstrip("?.!")
    match=re.fullmatch(
        r"(?:spark,? )?(?:please )?(?:search|find|look up) "
        r"(?:my|the) (?:knowledge|documents|notes) (?:for|about) "
        r"([\w .-]{2,100})",
        utterance,flags=re.IGNORECASE,
    )
    if not match:
        return None
    query=match.group(1).strip()
    if re.search(r"\b(?:then|and|open|run|execute|delete|remove|powershell|cmd)\b",query,re.I):
        return None
    return query if query else None
