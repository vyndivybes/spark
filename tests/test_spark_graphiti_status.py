import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'spark_graphiti_sidecar', Path(__file__).resolve().parents[1] / 'backend/spark_graphiti_mcp.py')
sidecar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sidecar)


class GraphStatusTests(unittest.TestCase):
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
