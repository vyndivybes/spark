"""Tests for the Neural Atlas Graphify bridge: extraction, vault generation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from spark_neural_atlas import (  # noqa: E402
    AtlasDataError,
    atlas_data_path,
    build_vault,
    choose_node_names,
    extract_inventory,
    generate_vault,
    links_by_node,
    node_markdown,
)

INVENTORY = {
    "schema_version": "1.0",
    "nodes": [
        {"id": "org-vayu", "title": "V\u0101yu Shastr", "type": "organization",
         "summary": "Core business ecosystem.", "status": "active-project",
         "confidence": "historical", "source_ids": ["s-history"],
         "tags": ["founder"], "properties": {"Knowledge owner": "Founder"},
         "updated_at": "2026-10-18", "timeline": [
             {"date": "2026-09-23", "text": "NDA received", "source_id": "s-email"}]},
        {"id": "prj-vaos", "title": "VAOS", "type": "project",
         "summary": "Business automation OS.", "status": "active-project",
         "confidence": "historical", "source_ids": [], "tags": ["software"],
         "properties": {}, "updated_at": "2026-10-18", "timeline": []},
        {"id": "prj-vyndios", "title": "INDEX", "type": "project",
         "summary": "", "status": "active-project", "confidence": "historical",
         "source_ids": [], "tags": [], "properties": {}, "updated_at": "",
         "timeline": []},
    ],
    "edges": [
        {"source": "org-vayu", "target": "prj-vaos"},
        {"source": "prj-vaos", "target": "prj-vyndios"},
        {"source": "org-vayu", "target": "org-vayu"},
    ],
    "sources": [
        {"id": "s-history", "title": "Chat history", "kind": "chat-history",
         "url": "", "event_date": "2026-10-18", "observed_at": "2026-10-18",
         "scope": "historical-summary", "note": "Summarised earlier context"},
        {"id": "s-email", "title": "Email thread", "kind": "email", "url": "",
         "event_date": "2026-09-23", "observed_at": "2026-09-23", "scope": "full",
         "note": ""},
    ],
}


def anchoring(index: dict) -> str:
    payload = json.dumps(index, ensure_ascii=False)
    return f'<html><script id="initial-data" type="application/json">{payload}</script></html>'


class ExtractInventory(unittest.TestCase):
    def test_extracts_and_validates_the_embedded_json(self):
        inventory = extract_inventory(anchoring(INVENTORY))
        self.assertEqual([n["id"] for n in inventory["nodes"]],
                         ["org-vayu", "prj-vaos", "prj-vyndios"])

    def test_missing_anchor_raises_clean_error(self):
        with self.assertRaises(AtlasDataError) as ctx:
            extract_inventory("<html></html>")
        self.assertIn("anchor", str(ctx.exception))

    def test_invalid_json_raises_clean_error(self):
        broken = '<script id="initial-data" type="application/json">{oops}</script>'
        with self.assertRaises(AtlasDataError) as ctx:
            extract_inventory(broken)
        self.assertIn("JSON", str(ctx.exception))

    def test_edge_to_unknown_node_rejected(self):
        inventory = {"nodes": [{"id": "a", "type": "project"}], "edges": [], "sources": []}
        anchored = anchoring({**inventory, "edges": [{"source": "a", "target": "ghost"}]})
        with self.assertRaises(AtlasDataError) as ctx:
            extract_inventory(anchored)
        self.assertIn("unknown node", str(ctx.exception))

    def test_empty_page_rejected(self):
        with self.assertRaises(AtlasDataError):
            extract_inventory("   ")


class VaultGeneration(unittest.TestCase):
    def setUp(self):
        self.inventory = extract_inventory(anchoring(INVENTORY))

    def test_writes_one_markdown_file_per_node_plus_overview(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "atlas-vault"
            result = generate_vault(self.inventory, vault)
            self.assertEqual(result["nodes"], 3)
            self.assertEqual(result["files"], 4)
            self.assertEqual(result["links"], 2)  # self-edge ignored
            self.assertTrue((vault / "CLAUDE.md").is_file())
            self.assertTrue((vault / "projects" / "VAOS.md").is_file())
            self.assertTrue((vault / "projects" / "prj-vyndios.md").is_file())

    def test_rebuild_replaces_stale_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "atlas-vault"
            vault.mkdir()
            (vault / "orders" / "old.md").parent.mkdir(parents=True)
            (vault / "orders" / "old.md").write_text("stale", encoding="utf-8")
            generate_vault(self.inventory, vault)
            self.assertFalse((vault / "orders" / "old.md").exists())
            self.assertFalse((vault / "orders").exists())

    def test_node_markdown_carries_graph_links_and_details(self):
        links = links_by_node(self.inventory)
        org = self.inventory["nodes"][0]
        text = node_markdown(self.inventory, links, choose_node_names(self.inventory), org)
        self.assertIn("[[VAOS]]", text)
        self.assertNotIn("[[Vayu-Shastr]]", text)  # self-edges are dropped
        self.assertIn("status: active-project", text)
        self.assertIn("NDA received", text)
        self.assertIn("Chat history (s-history)", text)
        self.assertIn("Knowledge owner: Founder", text)

    def test_titles_preferred_with_unique_stems(self):
        names = choose_node_names(self.inventory)
        self.assertEqual(names["prj-vaos"], "VAOS")
        self.assertEqual(names["org-vayu"], "Vayu-Shastr")
        self.assertNotEqual(names["org-vayu"], names["prj-vyndios"])

    def test_overview_points_at_vaos_and_vyndios(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "atlas-vault"
            generate_vault(self.inventory, vault)
            overview = (vault / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("[[prj-vaos]]" if "VAOS" not in overview else "[[VAOS]]", overview)
            self.assertIn("[[Vayu-Shastr]]", overview)

    def test_end_to_end_from_packaged_page(self):
        root = Path(__file__).resolve().parent.parent
        html_path = atlas_data_path(root)
        if not html_path.is_file():
            self.skipTest("packaged VAYU workspace page not checked out")
        with tempfile.TemporaryDirectory() as tmp:
            result = build_vault(root, tmp)
            self.assertGreater(result["nodes"], 100)
            self.assertGreater(result["links"], 100)
            vaos = list(Path(tmp).glob("projects/VAOS.md"))
            self.assertTrue(vaos)

    def test_holo_published_notes_flow_stays_intact(self):
        source = (BACKEND.parent / "electron" / "main.js").read_text(encoding="utf-8")
        self.assertIn("SPARK_NOTES_DIR", source)
        plan_source = (BACKEND.parent / "electron" / "experience-manager.cjs").read_text(
            encoding="utf-8")
        self.assertIn("SPARK_HOLO_NOTES_DIR", plan_source)
        self.assertIn("sample-notes", plan_source)


if __name__ == "__main__":
    unittest.main()
