"""Stage-7 native Google Search grounding: explicit zero-surprise opt-in."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from spark_live_profile import live_profile, select_live_config
from spark_grounding import extract_grounding_sources

class GroundingTests(unittest.TestCase):
    def test_known_good_profiles_never_trigger_google_search(self):
        full={"tools":[{"danger":"not_allowed"}]}
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(live_profile(),"cinematic")
        for profile in ("voice","cinematic","cinematic_tools"):
            self.assertNotIn("google_search",str(select_live_config(profile,full)))

    def test_search_requires_explicit_flag_and_never_activates_paid_account_billing(self):
        with patch.dict("os.environ",{"SPARK_LIVE_PROFILE":"cinematic_search"},clear=True):
            self.assertEqual(live_profile(),"cinematic_tools")
        with patch.dict("os.environ",{"SPARK_LIVE_PROFILE":"cinematic_search",
                                      "SPARK_ENABLE_GOOGLE_SEARCH":"1"},clear=True):
            self.assertEqual(live_profile(),"cinematic_search")

    def test_search_adds_only_built_in_google_grounding_and_existing_two_functions(self):
        with patch.dict("os.environ",{"SPARK_ENABLE_GOOGLE_SEARCH":"1"},clear=True):
            search=select_live_config("cinematic_search",{"tools":[{"danger":"not_allowed"}]})
            baseline=select_live_config("cinematic_tools",{})
            self.assertEqual(search["speech_config"],baseline["speech_config"])
            self.assertEqual(search["response_modalities"],["AUDIO"])
            self.assertEqual(search["tools"][0],{"google_search":{}})
            self.assertEqual(search["tools"][1],baseline["tools"][0])
            self.assertEqual(len(search["tools"]),2)
            self.assertIn("source",search["system_instruction"].lower())

    def test_search_without_enable_flag_cannot_assemble_billable_tool(self):
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaises(ValueError):
                select_live_config("cinematic_search",{})

    def test_extract_grounding_only_provider_supplied_https_sources(self):
        def chunk(title,url):
            return SimpleNamespace(web=SimpleNamespace(title=title,uri=url))
        m=SimpleNamespace(grounding_chunks=[
            chunk("NASA Artemis","https://www.nasa.gov/artemis"),
            chunk("NASA Artemis","https://www.nasa.gov/artemis"),
            chunk("unsafe","javascript:alert(1)"),
            chunk("bad","https://user:password@example.com/item"),
            chunk("Reuters","https://www.reuters.com/world/space/")
        ])
        self.assertEqual(extract_grounding_sources(m),[
            {"title":"NASA Artemis","url":"https://www.nasa.gov/artemis"},
            {"title":"Reuters","url":"https://www.reuters.com/world/space/"}])

    def test_sources_handle_missing_metadata_and_cap_at_five(self):
        self.assertEqual(extract_grounding_sources(None),[])
        c=[SimpleNamespace(web=SimpleNamespace(title=f"News {n}",uri=f"https://example.com/{n}"))
           for n in range(30)]
        self.assertEqual(len(extract_grounding_sources(SimpleNamespace(grounding_chunks=c))),5)

if __name__=="__main__":
    unittest.main()
