import os
import ast
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_live_config import live_model, live_status, live_error_message,live_error_requires_user_action,live_status_report


class LiveConfigTests(unittest.TestCase):
    def test_current_free_tier_live_model_is_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(live_model(), "gemini-3.8-live")

    def test_explicit_supported_live_model_is_respected(self):
        with patch.dict(os.environ, {"SPARK_LIVE_MODEL": "gemini-3.1-flash-live-preview"}, clear=True):
            self.assertEqual(live_model(), "gemini-3.1-flash-live-preview")

    def test_old_ada_model_is_never_selected(self):
        with patch.dict(os.environ, {"SPARK_LIVE_MODEL": "models/gemini-2.5-flash-native-audio-preview-12-2025"}, clear=True):
            self.assertEqual(live_model(), "gemini-3.8-live")

    def test_credential_status_does_not_expose_key(self):
        value = live_status(True, "gemini-3.8-live")
        self.assertEqual(value["state"], "idle")
        self.assertEqual(value["model"], "gemini-3.8-live")
        missing = live_status(False, "gemini-3.8-live")
        self.assertEqual(missing["state"], "setup_required")
        self.assertNotIn("secret-example", str(missing))

    def test_websocket_1008_policy_violation_is_distinct_from_quota(self):
        result = live_error_message(Exception(
            "received 1008 (policy violation) Requested entity was not found."
        ))
        self.assertIn("policy", result.lower())
        self.assertNotIn("429", result)

    def test_live_error_categories_never_include_private_provider_body(self):
        for raw, expected in [
            ("Error HTTP 429: secret-example quota exceeded", "rate limit"),
            ("Error HTTP 403: secret-example", "permission"),
            ("Error HTTP 404: secret-example", "model"),
            ("Some deep stack internal secret-example", "connection")
        ]:
            result = live_error_message(Exception(raw))
            self.assertIn(expected, result.lower())
            self.assertNotIn("secret-example", result)

    def test_taskgroup_policy_and_quota_errors_keep_their_category_and_stop_retry(self):
        for raw,category,code in [('1008 Requested entity was not found. secret-example','1008',1008),('429 quota exhausted secret-example','rate limit',429)]:
            error=ExceptionGroup('unhandled errors in a TaskGroup',[ExceptionGroup('nested',[RuntimeError(raw)])])
            message=live_error_message(error)
            self.assertIn(category,message)
            self.assertNotIn('secret-example',message)
            self.assertTrue(live_error_requires_user_action(error))
            self.assertEqual(live_status_report('error',message)['live_error_code'],code)

    def test_chained_errors_are_classified_and_transient_errors_remain_recoverable(self):
        error=RuntimeError('transport wrapper')
        error.__cause__=RuntimeError('403 access denied secret-example')
        self.assertIn('permission',live_error_message(error))
        self.assertTrue(live_error_requires_user_action(error))
        self.assertFalse(live_error_requires_user_action(RuntimeError('connection reset')))


class LiveRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def run_failure(self,error):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'backend/ada.py').read_text(encoding='utf-8'))
        audio=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='AudioLoop')
        method=next(node for node in audio.body if isinstance(node,ast.AsyncFunctionDef) and node.name=='run')
        calls=[];statuses=[]
        class FailedConnection:
            async def __aenter__(self):
                calls.append(True)
                raise error
            async def __aexit__(self,*args):return False
        scope={'asyncio':asyncio,'client':SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **kwargs:FailedConnection()))),
            'MODEL':'test','config':{},'live_profile':lambda:'cinematic',
            'pc_live_config':lambda config,enabled:config,'jarvis_live_config':lambda config,enabled:config,
            'live_error_message':live_error_message,'live_error_requires_user_action':live_error_requires_user_action}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'ada.py','exec'),scope)
        loop=SimpleNamespace(stop_event=asyncio.Event(),pc_access=None,jarvis_access=None,on_live_status=statuses.append)
        from unittest.mock import AsyncMock
        with patch('asyncio.sleep',new=AsyncMock()):
            await scope['run'](loop)
        return calls,statuses,loop

    async def test_grouped_policy_failure_stops_after_one_connection(self):
        calls,statuses,loop=await self.run_failure(ExceptionGroup('taskgroup',[RuntimeError('1008 Requested entity was not found')]))
        self.assertEqual(len(calls),1)
        self.assertEqual(statuses[-1]['state'],'error')
        self.assertIn('1008',statuses[-1]['message'])
        self.assertIsNone(loop.session)

    async def test_transient_failure_gets_only_one_reconnect(self):
        calls,statuses,loop=await self.run_failure(RuntimeError('connection reset'))
        self.assertEqual(len(calls),2)
        self.assertEqual(statuses[-1]['state'],'error')
        self.assertIsNone(loop.session)


if __name__ == "__main__":
    unittest.main()
