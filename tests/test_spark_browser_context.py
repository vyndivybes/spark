import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from spark_browser_session import explicit_page_context

class BrowserContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_snapshot_is_bounded_and_not_sent_to_model(self):
        page=MagicMock()
        page.url="https://example.org/safe"
        page.title=AsyncMock(return_value="My Site"+"x"*500)
        page.locator.return_value.inner_text=AsyncMock(return_value="visible "*1000)
        result=await explicit_page_context(page)
        self.assertEqual(result["model_transmission"],False)
        self.assertEqual(result["source"],"explicit_local_browser_inspection")
        self.assertEqual(len(result["title"]),180)
        self.assertEqual(len(result["visible_text"]),3000)
        page.locator.assert_called_once_with("body")

if __name__=="__main__":
    unittest.main()
