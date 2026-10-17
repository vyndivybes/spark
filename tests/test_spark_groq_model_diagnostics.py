"""Regression: Groq retired Llama-3.1-8b for free/developer accounts 2026-08-16."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from spark_groq import groq_model, classify_groq_http_error

class GroqDeprecationTests(unittest.TestCase):
    def test_default_uses_active_gpt_oss_20b(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(groq_model(),"openai/gpt-oss-20b")

    def test_explicit_legacy_model_is_rejected_not_silently_run(self):
        with patch.dict(os.environ,{"SPARK_GROQ_MODEL":"llama-3.1-8b-instant"},clear=True):
            with self.assertRaisesRegex(ValueError,"retired|deprecated"):
                groq_model()

    def test_unsupported_model_falls_back_to_current_supported_default(self):
        with patch.dict(os.environ,{"SPARK_GROQ_MODEL":"invalid-paid-model"},clear=True):
            self.assertEqual(groq_model(),"openai/gpt-oss-20b")

    def test_chat_404_explains_deprecated_model_without_showing_provider_body(self):
        message=str(classify_groq_http_error("chat",404))
        self.assertIn("chat",message.lower())
        self.assertIn("404",message)
        self.assertIn("openai/gpt-oss-20b",message)
        self.assertNotIn("api_key",message.lower())

    def test_provider_specific_stage_for_transcription_and_speech(self):
        stt=str(classify_groq_http_error("transcription",400))
        tts=str(classify_groq_http_error("speech",503))
        self.assertIn("transcription",stt.lower())
        self.assertIn("400",stt)
        self.assertIn("speech",tts.lower())
        self.assertIn("503",tts)
        self.assertNotIn("chat HTTP",tts)

    def test_rate_limit_never_transparently_falls_back_or_retries(self):
        msg=str(classify_groq_http_error("chat",429))
        self.assertIn("429",msg)
        self.assertIn("no automatic",msg.lower())

    def test_auth_issues_distinguishable_from_model_and_quota(self):
        self.assertIn("401",str(classify_groq_http_error("chat",401)))
        self.assertIn("403",str(classify_groq_http_error("chat",403)))
        self.assertIn("422",str(classify_groq_http_error("chat",422)))
        self.assertIn("500",str(classify_groq_http_error("chat",500)))

if __name__=="__main__":
    unittest.main()
