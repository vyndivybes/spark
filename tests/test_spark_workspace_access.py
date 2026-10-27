import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_workspace_auth import workspace_access_allowed


class WorkspaceAccessTests(unittest.TestCase):
    def test_local_workspace_requires_launch_token_without_requiring_voice(self):
        self.assertTrue(workspace_access_allowed('a'*64,'a'*64))
        for provided,expected in [(None,'a'*64),('b'*64,'a'*64),('',''),('a'*63,'a'*64),('a'*64,None)]:
            with self.subTest(provided_type=type(provided)):
                self.assertFalse(workspace_access_allowed(provided,expected))

    def test_face_lock_stays_enforced_even_with_valid_token(self):
        self.assertFalse(workspace_access_allowed('a'*64,'a'*64,face_required=True,face_authenticated=False))
        self.assertTrue(workspace_access_allowed('a'*64,'a'*64,face_required=True,face_authenticated=True))
        self.assertFalse(workspace_access_allowed('b'*64,'a'*64,face_required=True,face_authenticated=True))


class OfflineWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_socket_handler_keeps_repository_workflow_token_and_face_gated_without_audio(self):
        from unittest.mock import patch
        from tests.test_spark_evolution import EvolutionSocketTests
        with patch.dict('os.environ',{'SPARK_WORKSPACE_TOKEN':'a'*64}):
            for action,token,unlocked,expected in [
                ('analyze_repository','a'*64,True,True),
                ('preview_repository','a'*64,True,True),
                ('stage_repository_upgrade','a'*64,True,True),
                ('stage_repository_upgrade',None,True,False),
                ('stage_repository_upgrade','b'*64,True,False),
                ('stage_repository_upgrade','a'*64,False,False),
                ('list_repair_candidates','a'*64,True,True),
                ('list_repairs','a'*64,True,True),
                ('test_repair_candidate','a'*64,True,True),
                ('activate_repair_candidate','a'*64,True,True),
                ('rollback_repair','a'*64,True,True),
                ('test_repair_candidate',None,True,False),
                ('activate_repair_candidate','b'*64,True,False),
                ('activate_repair_candidate','a'*64,False,False),
                ('rollback_repair',None,True,False),
                ('preview_repository',None,True,False),
                ('analyze_repository',None,True,False),
                ('analyze_repository','a'*64,False,False),
                ('rea_discover','a'*64,True,False)]:
                with self.subTest(action=action,unlocked=unlocked,token_present=bool(token)):
                    namespace=EvolutionSocketTests().handler(authenticated=unlocked)
                    namespace['audio_loop']=None
                    await namespace['workspace_action']('desktop',{'request_id':'offline-test','action':action,
                        'workspace_token':token,'project':'general','payload':{}})
                    self.assertEqual(namespace['spark_evolution'].execute.await_count,int(expected))
                    self.assertEqual(namespace['sio'].emit.await_args.args[1]['ok'],expected)
