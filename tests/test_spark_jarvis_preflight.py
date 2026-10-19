"""Safe offline/opt-in live verification of SPARK -> VAOS Jarvis pairing."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from spark_jarvis_preflight import check_pairing


TOKEN = 'x' * 48
VALID = {
    'SPARK_JARVIS_URL': 'https://vaos.example',
    'SPARK_JARVIS_DEVICE_ID': 'spark-windows-1',
    'SPARK_JARVIS_TOKEN': TOKEN,
}


class PairingPreflightTests(unittest.TestCase):
    def test_offline_check_never_contacts_remote_or_discloses_secret(self):
        events = []
        class FakeBridge:
            def __init__(self, origin, token, device_id):
                events.append(('constructed', origin, device_id))
            def ask(self, question):
                raise AssertionError('offline preflight must never call the network')
        code, message = check_pairing(VALID, probe=False, bridge_factory=FakeBridge)
        self.assertEqual(code, 0)
        self.assertIn('NOT tested', message)
        self.assertNotIn(TOKEN, message)
        self.assertEqual(len(events), 1)

    def test_missing_or_invalid_config_is_hold(self):
        code, message = check_pairing({}, probe=False)
        self.assertNotEqual(code, 0)
        self.assertNotIn(TOKEN, message)
        code, message = check_pairing({**VALID, 'SPARK_JARVIS_URL': 'http://localhost:8000'}, probe=False)
        self.assertNotEqual(code, 0)

    def test_live_probe_is_explicit_and_only_asks_a_greeting(self):
        questions = []
        class FakeBridge:
            def __init__(self, *_): pass
            def ask(self, question):
                questions.append(question)
                return {'status':'READY', 'sourceSystem':'VAOS_CONVERSATION', 'answer':'Hello from VAOS Jarvis.'}
        code, message = check_pairing(VALID, probe=True, bridge_factory=FakeBridge)
        self.assertEqual(code, 0)
        self.assertEqual(questions, ['Hello from SPARK'])
        self.assertIn('greeting verified', message)
        self.assertIn('not verified', message.lower())
        self.assertNotIn(TOKEN, message)

    def test_holds_and_untrusted_greetings_cannot_claim_live_readiness(self):
        for result in [
            {'status':'HOLD','sourceSystem':'VAOS_CONVERSATION','answer':'Unavailable'},
            {'status':'READY','sourceSystem':'VYNDI_OS','answer':'Not a greeting'},
        ]:
            class FakeBridge:
                def __init__(self, *_): pass
                def ask(self, question): return result
            code, message = check_pairing(VALID, probe=True, bridge_factory=FakeBridge)
            self.assertNotEqual(code, 0)
            self.assertNotIn(TOKEN, message)

    def test_network_failure_is_reported_without_sensitive_data(self):
        class FakeBridge:
            def __init__(self, *_): pass
            def ask(self, question): raise OSError('Bearer '+TOKEN)
        code, message = check_pairing(VALID, probe=True, bridge_factory=FakeBridge)
        self.assertNotEqual(code, 0)
        self.assertNotIn(TOKEN, message)
        self.assertIn('failed', message.lower())


if __name__ == '__main__':
    unittest.main()
