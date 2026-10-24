import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('configure_integrations', ROOT / 'scripts/configure-integrations.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class IntegrationConfigurationTests(unittest.TestCase):
    def test_google_tools_preserve_existing_account_and_write_grants(self):
        original = {'gmail': {'command': 'python', 'args': [str(ROOT / 'backend/spark_google_mcp.py'), '--account', 'owner@example.com', '--allow-writes'],
                             'read_tools': ['google_list_items'], 'write_tools': ['google_save_email_draft']}}
        result = setup.complete_registry(original)
        self.assertIn('google_daily_briefing', result['gmail']['read_tools'])
        self.assertIn('google_search_email', result['gmail']['read_tools'])
        self.assertEqual(result['gmail']['args'], original['gmail']['args'])
        self.assertEqual(result['gmail']['write_tools'], original['gmail']['write_tools'])
        self.assertEqual(original['gmail']['read_tools'], ['google_list_items'])
        self.assertEqual(setup.complete_registry(result), result)

    def test_unrelated_google_adapter_does_not_gain_tools(self):
        original = {'gmail': {'args': ['other.py'], 'read_tools': []}}
        self.assertEqual(setup.complete_registry(original).get('gmail'), original['gmail'])

    def test_graphify_respects_catalog_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('.venv/Scripts/graphify-mcp.exe', 'graphify-out/graph.json'):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            self.assertIn('graphify', setup.complete_registry({}, root))
            full = {str(index): {} for index in range(8)}
            self.assertEqual(setup.complete_registry(full, root), full)

    def test_placeholders_and_missing_consents_never_become_configured(self):
        class Hub:
            def configure(self, *args):
                raise AssertionError('Incomplete accounts must not be configured')
        channels = setup.messaging_template()
        channels['telegram']['enabled'] = True
        channels['whatsapp'].update(enabled=True, access_token='secret', phone_number_id='123', allowed_recipient='456')
        report = setup.configure_messaging(Hub(), channels)
        self.assertEqual(report['telegram']['state'], 'setup_required')
        self.assertIn('understood_pricing', report['whatsapp']['missing'])
        self.assertNotIn('secret', str(report))

    def test_selected_slack_account_reuses_host_token_without_sending(self):
        calls = []
        class Hub:
            def configure(self, channel, config):
                calls.append((channel, config))
        report = setup.configure_messaging(Hub(), {'slack': {'enabled': True, 'allowed_channel': 'C123'}}, 'private-token')
        self.assertEqual(calls, [('slack', {'allowed_channel': 'C123', 'bot_token': 'private-token'})])
        self.assertEqual(report['slack']['state'], 'configured_untested')
        self.assertNotIn('private-token', str(report))


if __name__ == '__main__':
    unittest.main()
