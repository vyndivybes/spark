import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from spark_workspace_auth import workspace_client_allowed


class WorkspaceOriginTests(unittest.TestCase):
    def test_foreign_null_and_missing_origins_fail_closed(self):
        for origin in ('https://example.com', 'null', '', 'http://localhost:5173.evil.com'):
            self.assertFalse(workspace_client_allowed({'HTTP_ORIGIN':origin}, None, None))

    def test_dev_origin_and_desktop_nonce(self):
        self.assertTrue(workspace_client_allowed({'HTTP_ORIGIN':'http://localhost:5173'}, None, None))
        self.assertTrue(workspace_client_allowed({'HTTP_ORIGIN':'null'}, 'a'*64, 'a'*64))
        for token in (None, {}, 'a'*65, 'b'*64):
            self.assertFalse(workspace_client_allowed({}, token, 'a'*64))
