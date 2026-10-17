"""Provider-independent diagnostic snapshot must never return secrets or chat."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_diagnostics import safe_diagnostics

class DiagnosticsTests(unittest.TestCase):
 def test_bounded_whitelist_without_secrets(self):
  source={"service":"SPARK Core","ai_provider":"groq","live_state":"connected",
          "hands_free_ready":True,"groq_configured":True,
          "GROQ_API_KEY":"SECRET","api_key":"SECRET2",
          "conversation":"PRIVATE HISTORY","live_message":"SHOULD NOT BE COPIED",
          "live_error_code":"429"}
  d=safe_diagnostics(source,uptime_seconds=123)
  self.assertEqual(d["ai_provider"],"groq")
  self.assertEqual(d["live_error_code"],"429")
  self.assertEqual(d["uptime_seconds"],123)
  self.assertNotIn("GROQ_API_KEY",str(d))
  self.assertNotIn("SECRET",str(d))
  self.assertNotIn("PRIVATE",str(d))
  self.assertNotIn("live_message",d)
 def test_malformed_values_never_crash(self):
  d=safe_diagnostics({"live_state":{"bad":"state"},"ai_provider":"x"*10000,
                      "live_model":"line1\nline2","hands_free_ready":"yes"},uptime_seconds=-5)
  self.assertEqual(d["live_state"],"unknown")
  self.assertEqual(d["ai_provider"],"unknown")
  self.assertEqual(d["hands_free_ready"],False)
  self.assertEqual(d["uptime_seconds"],0)
  self.assertNotIn("\n",d["live_model"])
if __name__=="__main__":unittest.main()
