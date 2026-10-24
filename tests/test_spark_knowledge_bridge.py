import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from contextlib import closing

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_knowledge_bridge import project_knowledge
from spark_graphiti_mcp import TemporalGraph
from spark_graphiti_inventory import import_inventory, import_source_records


class KnowledgeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / 'workspace'
        self.vault = self.root / 'vault'
        self.vault.mkdir()
        (self.vault / 'VAOS.md').write_text('VAOS evidence must preserve release holds.', encoding='utf-8')
        page = self.root / 'vendor/vayu-workspace/VAYU-Knowledge-Sphere-Live.html'
        page.parent.mkdir(parents=True)
        inventory = {'nodes':[{'id':'vaos','title':'VAOS','type':'project'}], 'edges':[], 'sources':[]}
        page.write_text('<script id="initial-data" type="application/json">' + json.dumps(inventory) + '</script>', encoding='utf-8')
        snapshots = self.workspace / 'integration-sync/snapshots.sqlite3'
        snapshots.parent.mkdir(parents=True)
        with closing(sqlite3.connect(snapshots)) as db, db:
            db.execute('CREATE TABLE snapshots(service,tool,body,last_success,state)')
            db.execute('INSERT INTO snapshots VALUES(?,?,?,?,?)', ('vyndi-os','read_vyndi_engineering_authority',json.dumps({'limitation':'Seeded reference only','data':{'hold':True}}),1000,'failed'))
            db.execute('INSERT INTO snapshots VALUES(?,?,?,?,?)', ('gmail','google_list_items',json.dumps({'private':'unrelated mail'}),1000,'current'))

    def tearDown(self):
        self.tmp.cleanup()

    def project(self, project='default'):
        return project_knowledge(self.workspace, project, self.vault, self.root)

    def test_projection_preserves_notes_provenance_holds_and_is_idempotent(self):
        first = self.project()
        second = self.project()
        self.assertEqual(first['records'], 3)
        self.assertEqual(second['episodes_staged'], 3)
        self.assertEqual((self.vault / 'VAOS.md').read_text(), 'VAOS evidence must preserve release holds.')
        text = '\n'.join(p.read_text(encoding='utf-8') for p in Path(first['vault_folder']).glob('*.md'))
        self.assertIn('Reader state: failed', text)
        self.assertIn('Seeded reference only', text)
        self.assertNotIn('unrelated mail', text)
        self.assertIn('[[Spark-Connected/default/Spark connected knowledge|Spark connected knowledge]]', text)
        snapshots = self.workspace / 'integration-sync/snapshots.sqlite3'
        with closing(sqlite3.connect(snapshots)) as db, db:
            db.execute('UPDATE snapshots SET last_success=2000')
        self.assertEqual(self.project()['episodes_staged'], 3)

    def test_changed_notes_produce_history_and_graphiti_only_reads_selected_project(self):
        self.project()
        (self.vault / 'VAOS.md').write_text('VAOS new decision at source.', encoding='utf-8')
        self.assertEqual(self.project()['episodes_staged'], 4)
        self.project('other')
        graph = TemporalGraph(self.workspace, self.workspace / 'graphiti')
        try:
            self.assertEqual(graph._pending('missing', 100), [])
            pending = graph._pending('default', 100)
            self.assertEqual(len(pending), 4)
            self.assertTrue(any('new decision' in row[1] for row in pending))
            with graph._manifest:
                graph._manifest.execute('INSERT INTO ingested VALUES(?,?,?,?)', (pending[0][3], 'default', 'episode', 1000))
            self.assertEqual(len(graph._pending('default', 100)), 3)
            self.assertEqual(len(graph._pending('other', 100)), 3)
        finally:
            graph._manifest.close()

    def test_invalid_project_never_creates_export(self):
        with self.assertRaises(ValueError):
            self.project('../outside')
        self.assertFalse((self.vault / 'Spark-Connected').exists())

    def test_native_inventory_import_is_source_labelled_and_idempotent(self):
        self.project()
        graph = TemporalGraph(self.workspace, self.workspace / 'graphiti')
        save = AsyncMock()
        client = SimpleNamespace(driver=object(), embedder=object())
        graph._client = AsyncMock(return_value=client)
        modules = {'graphiti_core.nodes':SimpleNamespace(EntityNode=SimpleNamespace, EpisodicNode=SimpleNamespace, EpisodeType=SimpleNamespace(text='text')),
                   'graphiti_core.edges':SimpleNamespace(EntityEdge=SimpleNamespace, EpisodicEdge=SimpleNamespace),
                   'graphiti_core.utils.bulk_utils':SimpleNamespace(add_nodes_and_edges_bulk=save)}
        try:
            with patch.dict(sys.modules, modules):
                result = asyncio.run(import_inventory(graph, 'default', self.root))
                again = asyncio.run(import_inventory(graph, 'default', self.root))
            self.assertEqual(result['episodes_added'], 1)
            self.assertEqual(again['episodes_added'], 0)
            self.assertEqual(len(graph._pending('default', 100)), 2)
            episodes = save.await_args_list[0].args[1]
            self.assertIn('not a live business ledger', episodes[0].source_description)
            node = save.await_args_list[1].args[3][0]
            self.assertEqual(node.attributes['source_kind'], 'packaged-reference')
        finally:
            graph._manifest.close()

    def test_failed_native_save_never_marks_source_ingested(self):
        self.project()
        graph = TemporalGraph(self.workspace, self.workspace / 'graphiti')
        graph._client = AsyncMock(return_value=SimpleNamespace(driver=object(), embedder=object()))
        modules = {'graphiti_core.nodes':SimpleNamespace(EntityNode=SimpleNamespace, EpisodicNode=SimpleNamespace, EpisodeType=SimpleNamespace(text='text')),
                   'graphiti_core.edges':SimpleNamespace(EntityEdge=SimpleNamespace, EpisodicEdge=SimpleNamespace),
                   'graphiti_core.utils.bulk_utils':SimpleNamespace(add_nodes_and_edges_bulk=AsyncMock(side_effect=RuntimeError('unavailable')))}
        try:
            with patch.dict(sys.modules, modules):
                with self.assertRaises(RuntimeError):
                    asyncio.run(import_inventory(graph, 'default', self.root))
            self.assertEqual(len(graph._pending('default', 100)), 3)
        finally:
            graph._manifest.close()

    def test_cached_business_sources_preserve_reader_failure_and_never_infer_business_approval(self):
        self.project()
        graph = TemporalGraph(self.workspace,self.workspace/'graphiti')
        save = AsyncMock()
        graph._client = AsyncMock(return_value=SimpleNamespace(driver=object(),embedder=object()))
        modules = {'graphiti_core.nodes':SimpleNamespace(EntityNode=SimpleNamespace,EpisodicNode=SimpleNamespace,EpisodeType=SimpleNamespace(text='text')),
                   'graphiti_core.edges':SimpleNamespace(EntityEdge=SimpleNamespace,EpisodicEdge=SimpleNamespace),
                   'graphiti_core.utils.bulk_utils':SimpleNamespace(add_nodes_and_edges_bulk=save)}
        try:
            with patch.dict(sys.modules,modules):
                result = asyncio.run(import_source_records(graph,'default'))
                again = asyncio.run(import_source_records(graph,'default'))
            self.assertEqual(result['episodes_added'],1)
            self.assertEqual(again['episodes_added'],0)
            snapshot = save.await_args_list[0].args[3][1]
            self.assertIn('Reader state: failed',snapshot.summary)
            self.assertIn('Seeded reference only',snapshot.summary)
            self.assertEqual(snapshot.attributes['source_kind'],'cached-business-evidence')
            edge = save.await_args_list[0].args[4][0]
            self.assertEqual(edge.name,'HAS_CACHED_EVIDENCE')
            self.assertEqual(len(graph._pending('default',100)),2)
        finally:
            graph._manifest.close()


if __name__ == '__main__':
    unittest.main()
