import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'spark_graphiti_sidecar', Path(__file__).resolve().parents[1] / 'backend/spark_graphiti_mcp.py')
sidecar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sidecar)


class GraphStatusTests(unittest.TestCase):
    def test_strict_schema_keeps_nullable_fields_and_does_not_mutate_model_schema(self):
        schema = {'type':'object', 'properties':{'fact':{'type':'string'},
                  'valid_at':{'anyOf':[{'type':'string'},{'type':'null'}], 'default':None}},
                  'required':['fact']}
        result = sidecar.strict_schema(schema)
        self.assertEqual(set(result['required']), {'fact','valid_at'})
        self.assertFalse(result['additionalProperties'])
        self.assertIn({'type':'null'}, result['properties']['valid_at']['anyOf'])
        self.assertNotIn('default', result['properties']['valid_at'])
        self.assertEqual(schema['required'], ['fact'])
        self.assertIn('default', schema['properties']['valid_at'])

    def test_status_checks_installation_without_loading_inference_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            graph = sidecar.TemporalGraph(Path(directory) / 'workspace', Path(directory) / 'graph')
            try:
                with patch.object(sidecar.importlib.util, 'find_spec', return_value=object()) as probe:
                    with patch.dict(os.environ, {'GROQ_API_KEY':'fixture', 'GEMINI_API_KEY':'fixture'}):
                        status = graph.status()
                self.assertTrue(status['installed'])
                self.assertTrue(status['credentials_configured'])
                self.assertEqual([call.args[0] for call in probe.call_args_list], ['graphiti_core', 'kuzu'])
                self.assertIsNone(graph._graphiti)
                self.assertNotIn('fixture', str(status))
                with patch.object(sidecar.importlib.util, 'find_spec', return_value=None):
                    self.assertFalse(graph.status()['installed'])
            finally:
                graph._manifest.close()


class GraphRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_quota_response_stops_batch_and_keeps_all_records_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            graph = sidecar.TemporalGraph(Path(directory) / 'workspace', Path(directory) / 'graph')
            add = AsyncMock(side_effect=sidecar.GraphitiRateLimited('Groq extraction rate limit reached.'))
            graph._client = AsyncMock(return_value=SimpleNamespace(add_episode=add))
            pending = [('bridge:one','VAOS evidence',1000,'one'), ('bridge:two','VEDM evidence',1001,'two')]
            try:
                with patch.dict(sys.modules, {'graphiti_core.nodes':SimpleNamespace(EpisodeType=SimpleNamespace(text='text'))}):
                    with patch.object(graph, '_pending', return_value=pending):
                        result = await graph.refresh('default')
                self.assertEqual(add.await_count, 1)
                self.assertEqual(add.await_args.kwargs['previous_episode_uuids'], [])
                self.assertEqual(result['episodes_failed'], 1)
                self.assertEqual(result['remaining'], 2)
                self.assertEqual(graph._manifest.execute('SELECT count(*) FROM ingested').fetchone()[0], 0)
            finally:
                graph._manifest.close()

    async def test_timeout_retains_pending_record_without_marking_it_ingested(self):
        with tempfile.TemporaryDirectory() as directory:
            graph = sidecar.TemporalGraph(Path(directory) / 'workspace', Path(directory) / 'graph')
            async def slow_episode(**kwargs):
                await asyncio.sleep(60)
            graph._client = AsyncMock(return_value=SimpleNamespace(add_episode=slow_episode))
            pending = [('source', 'VAOS test evidence', 1000, 'record')]
            actual_wait_for = asyncio.wait_for
            async def limited_wait(coro, timeout):
                return await actual_wait_for(coro, .001)
            try:
                with patch.dict(sys.modules, {'graphiti_core.nodes':SimpleNamespace(EpisodeType=SimpleNamespace(text='text'))}):
                    with patch.object(graph, '_pending', return_value=pending):
                        with patch.object(sidecar.asyncio, 'wait_for', new=limited_wait):
                            result = await graph.refresh('default')
                self.assertTrue(result['time_limit_reached'])
                self.assertEqual(result['episodes_added'], 0)
                self.assertEqual(result['remaining'], 1)
                self.assertEqual(graph._manifest.execute('SELECT count(*) FROM ingested').fetchone()[0], 0)
            finally:
                graph._manifest.close()
