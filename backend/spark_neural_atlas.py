"""Neural Atlas data bridge: render the local Graphify business graph as a
markdown vault so the Brain Map viewer shows real VAOS/Vyndios data instead of
the sample notes vault.

The Graphify inventory is embedded in the VAYU workspace page
(``<script id="initial-data" type="application/json">``) by the upstream data
file. Reading it from there keeps one canonical source: nothing is duplicated
and no third-party editing tool is invoked. Extraction and generation are
pure functions over read-only inputs; generation only ever writes into the
dedicated atlas vault directory the caller passes in.
"""
import json
import re
import shutil
import unicodedata
from pathlib import Path

INVENTORY_ANCHOR = re.compile(
    r'<script id="initial-data" type="application/json">\s*(\{.*?\})\s*</script>',
    re.DOTALL,
)

# Brain Map groups by a node file's top-level directory, so one directory per
# Graphify node type gives the atlas stable, labelled clusters. Anything new
# upstream still renders (unknown types share one folder instead of breaking).
TYPE_DIRS = {
    "organization": "organizations",
    "division": "divisions",
    "project": "projects",
    "contact": "contacts",
    "document": "documents",
    "decision": "decisions",
    "record": "records",
}
FALLBACK_DIR = "others"


class AtlasDataError(ValueError):
    """The packaged Graphify inventory could not be read or is inconsistent."""


def extract_inventory(html_text: str) -> dict:
    if not isinstance(html_text, str) or not html_text.strip():
        raise AtlasDataError("VAYU workspace page is empty.")
    match = INVENTORY_ANCHOR.search(html_text)
    if not match:
        raise AtlasDataError("Graphify inventory anchor not found in VAYU workspace page.")
    try:
        inventory = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise AtlasDataError(f"Graphify inventory is not valid JSON: {error}") from error
    _validate(inventory)
    return inventory


def _validate(inventory: dict) -> None:
    if not isinstance(inventory, dict):
        raise AtlasDataError("Graphify inventory must be a JSON object.")
    nodes = inventory.get("nodes")
    edges = inventory.get("edges")
    sources = inventory.get("sources", [])
    if not isinstance(nodes, list) or not nodes:
        raise AtlasDataError("Graphify inventory has no nodes.")
    if not isinstance(edges, list):
        raise AtlasDataError("Graphify inventory has no edge list.")
    if not isinstance(sources, list):
        raise AtlasDataError("Graphify inventory sources list is invalid.")
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"].strip():
            raise AtlasDataError("Graphify node without an id.")
    known = {node["id"] for node in nodes}
    for edge in edges:
        if not isinstance(edge, dict):
            raise AtlasDataError("Graphify inventory edge is not an object.")
        if edge.get("source") not in known or edge.get("target") not in known:
            raise AtlasDataError(
                f"Edge {edge.get('source')!r} -> {edge.get('target')!r} references an unknown node.")


def _safe_filename(value: str) -> str:
    transliterated = unicodedata.normalize("NFKD", value).encode(
        "ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", transliterated).strip("-. ")
    return re.sub(r"-{2,}", "-", cleaned) or "node"


def choose_node_names(inventory: dict) -> dict:
    """Map each node id to a markdown filename stem (their atlas label).

    Titles are easier to read in the graph view, so they are preferred; ids
    remain the fallback so every stem stays unique and wiki links resolve.
    """
    used = set()
    names = {}
    for node in inventory["nodes"]:
        title = str(node.get("title") or "").strip()
        candidates = []
        if title:
            candidates.append(_safe_filename(title))
        candidates.append(_safe_filename(node["id"]))
        name = candidates[0]
        if name.lower() in titles_RESERVED_STEMS:
            # Reserved stems (SKILL/INDEX/...) get special Brain Map treatment;
            # fall back to the stable id-derived name instead.
            name = candidates[-1]
        stem = name
        suffix = 2
        while stem.lower() in used:
            stem = f"{name}-{suffix}"
            suffix += 1
        names[node["id"]] = stem
        used.add(stem.lower())
    return names


titles_RESERVED_STEMS = {"skill", "readme", "index"}


def links_by_node(inventory: dict) -> dict:
    """Directed graphify edges grouped per node id (both endpoints validated).

    Self-edges (a node linking to itself) are dropped: Brain Map ignores
    same-file wiki links, so counting or writing them would only mislead.
    """
    links = {}
    for edge in inventory.get("edges", []):
        if edge["source"] == edge["target"]:
            continue
        links.setdefault(edge["source"], set()).add(edge["target"])
    return links


def _source_lines(inventory: dict, node: dict) -> list:
    by_id = {source.get("id"): source
             for source in inventory.get("sources", [])
             if isinstance(source, dict) and source.get("id")}
    lines = []
    for source_id in node.get("source_ids") or []:
        source = by_id.get(source_id)
        if source:
            note = str(source.get("note") or "").strip()
            title = str(source.get("title") or "").strip() or source_id
            suffix = f" — {note}" if note else ""
            lines.append(f"- {title} ({source_id}){suffix}")
        else:
            lines.append(f"- {source_id} (unresolved)")
    return lines


def _timeline_lines(node: dict) -> list:
    lines = []
    for entry in node.get("timeline") or []:
        if not isinstance(entry, dict):
            continue
        date = str(entry.get("date") or "").strip()
        text = str(entry.get("text") or "").strip()
        source = str(entry.get("source_id") or "").strip()
        parts = [part for part in (date, text, f"({source})" if source else "") if part]
        if parts:
            lines.append(f"- {' · '.join(parts)}")
    return lines


def _property_lines(node: dict) -> list:
    properties = node.get("properties")
    if not isinstance(properties, dict):
        return []
    lines = []
    for key, value in properties.items():
        if isinstance(value, (dict, list, tuple, set)):
            rendered = json.dumps(value, ensure_ascii=False)
        else:
            rendered = str(value)
        lines.append(f"- {key}: {rendered}")
    return lines


def node_markdown(inventory: dict, links: dict, names: dict, node: dict) -> str:
    node_type = str(node.get("type") or "unknown").strip() or "unknown"
    title = str(node.get("title") or node["id"]).strip() or node["id"]
    lines = [f"# {title}", ""]
    meta = [node_type]
    for key in ("status", "confidence", "updated_at"):
        value = str(node.get(key) or "").strip()
        if value:
            meta.append(f"{key.replace('_', ' ')}: {value}")
    if summary := str(node.get("summary") or "").strip():
        lines.append(summary)
        lines.append("")
    if meta:
        lines.append(", ".join(meta))
        lines.append("")
    tags = [str(tag).strip() for tag in (node.get("tags") or []) if str(tag).strip()]
    if tags:
        lines.append("Tags: " + ", ".join(tags))
        lines.append("")
    targets = sorted(links.get(node["id"], ()))
    if targets:
        lines.append("Related in the graph:")
        lines.extend(f"- [[{names[target]}]]" for target in targets)
        lines.append("")
    if property_lines := _property_lines(node):
        lines.append("Properties:")
        lines.extend(property_lines)
        lines.append("")
    if timeline_lines := _timeline_lines(node):
        lines.append("Timeline:")
        lines.extend(timeline_lines)
        lines.append("")
    if source_lines := _source_lines(inventory, node):
        lines.append("Sources:")
        lines.extend(source_lines)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def overview_markdown(inventory: dict, links: dict, names: dict) -> str:
    nodes = inventory["nodes"]
    by_id = {node["id"]: node for node in nodes}
    def titled(node_id):
        return f"- [[{names[node_id]}]]" if node_id in by_id else ""
    ovayu = titled("org-vayu") or ""
    vvaos = titled("prj-vaos") or ""
    vvyndios = titled("prj-vyndios") or ""
    counts = ", ".join(
        f"{count} {node_type}" for node_type, count in sorted(
            {str(n.get("type") or "unknown"): 0 for n in nodes}.items()))
    total = len(nodes)
    edge_count = len(inventory.get("edges", []))
    source_count = len(inventory.get("sources", []))
    lines = [
        "# Neural Atlas",
        "",
        "This vault is generated from the local Graphify business inventory.",
        "It replaces the sample notes so the atlas maps the real VAOS/Vyndios",
        "workspace: the organisation, its divisions, projects, contacts,",
        "documents, decisions and event records, with every graph edge as a",
        "wiki link.",
        "",
        f"Inventory snapshot: {total} nodes, {edge_count} edges, {source_count} sources ({counts}).",
        "",
        "Start from:",
        ovayu,
        vvaos,
        vvyndios,
        "",
        "Only this generated vault is mapped here; HOLO keeps its own",
        "published-notes folder and VAYU actions stay separate.",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def generate_vault(inventory: dict, vault_dir) -> dict:
    """Write one markdown file per graphify node plus an overview.

    Returns {"nodes", "links", "files"}. The vault directory is engine-owned:
    an existing directory is cleared so rebuilt atlases never show stale nodes
    that upstream no longer lists.
    """
    if not isinstance(inventory, dict) or not inventory.get("nodes"):
        raise AtlasDataError("Cannot generate an atlas vault without an inventory.")
    vault = Path(vault_dir)
    if vault.exists():
        shutil.rmtree(vault)
    (vault / "CLAUDE.md").parent.mkdir(parents=True, exist_ok=True)
    links = links_by_node(inventory)
    names = choose_node_names(inventory)
    files = 0
    link_targets = 0
    by_id = {node["id"] for node in inventory["nodes"]}
    for node in inventory["nodes"]:
        node_dir = vault / TYPE_DIRS.get(str(node.get("type") or ""), FALLBACK_DIR)
        node_dir.mkdir(parents=True, exist_ok=True)
        (node_dir / f"{names[node['id']]}.md").write_text(
            node_markdown(inventory, links, names, node), encoding="utf-8")
        files += 1
        link_targets += len({t for t in links.get(node["id"], set()) if t in by_id})
    (vault / "CLAUDE.md").write_text(overview_markdown(inventory, links, names), encoding="utf-8")
    files += 1
    return {"nodes": len(inventory["nodes"]), "links": link_targets, "files": files}


def atlas_data_path(root) -> Path:
    return Path(root) / "vendor" / "vayu-workspace" / "VAYU-Knowledge-Sphere-Live.html"


def build_vault(root, vault_dir) -> dict:
    html_path = atlas_data_path(root)
    try:
        html_text = html_path.read_text(encoding="utf-8")
    except OSError as error:
        raise AtlasDataError(f"Cannot read the VAYU workspace page: {error}") from error
    inventory = extract_inventory(html_text)
    return generate_vault(inventory, vault_dir)
