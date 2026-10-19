"""Read-only Jarvis client acceptance tests. No live network or credentials."""
import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_jarvis_bridge import JarvisBridge, JarvisBridgeError, local_bridge_client_allowed

class Reply:
    status=200
    def __init__(self,payload): self.stream=io.BytesIO(json.dumps(payload).encode())
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def read(self,n):return self.stream.read(n)

class BridgeTests(unittest.TestCase):
    def test_requires_https_fixed_origin_and_secret(self):
        for endpoint in ('http://vaos.example','https://vaos.example/path','https://user:pw@vaos.example'):
            with self.assertRaises(JarvisBridgeError):JarvisBridge(endpoint,'x'*40,'spark-windows-1')
        with self.assertRaises(JarvisBridgeError):JarvisBridge('https://vaos.example','short','spark-windows-1')
    def test_valid_request_uses_fixed_path_credentials_and_timeout(self):
        def open_request(request,timeout):
            self.assertEqual(request.full_url,'https://vaos.example/api/spark-bridge')
            self.assertEqual(request.get_header('Authorization'),'Bearer '+'x'*40)
            self.assertEqual(timeout,8)
            body=json.loads(request.data)
            return Reply({'data':{'requestId':body['requestId'],'readOnly':True,'actionAuthorized':False,
                'schemaVersion':'SPARK_JARVIS_V1','businessEffectsExecuted':False,
                'answer':'2 inventory records in selected window','status':'OBSERVED','sourceAuthority':'getAuthoritativeInventory'}})
        c=JarvisBridge('https://vaos.example','x'*40,'spark-windows-1',opener=open_request)
        result=c.ask('How many stock items are recorded?')
        self.assertEqual(result['status'],'OBSERVED')
        self.assertEqual(result['sourceAuthority'],'getAuthoritativeInventory')
    def test_write_commands_and_bad_reply_denied(self):
        c=JarvisBridge('https://vaos.example','x'*40,'spark-windows-1',opener=lambda *a,**k:Reply({'data':{'actionAuthorized':True}}))
        with self.assertRaises(JarvisBridgeError):c.ask('Delete all records')
        with self.assertRaises(JarvisBridgeError):c.ask('How many sales orders?')
    def test_local_desktop_session_requires_real_token_and_trusted_origin(self):
        actual='a'*64
        self.assertTrue(local_bridge_client_allowed({'HTTP_ORIGIN':'http://localhost:5173'},actual,actual))
        self.assertFalse(local_bridge_client_allowed({'HTTP_ORIGIN':'http://localhost:5173'},'b'*64,actual))
        self.assertFalse(local_bridge_client_allowed({'HTTP_ORIGIN':'https://other.example'},actual,actual))
        self.assertFalse(local_bridge_client_allowed({'HTTP_ORIGIN':'http://localhost:5173'},None,actual))
    def test_no_configuration_is_explicitly_unavailable(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(JarvisBridgeError):JarvisBridge.from_environment()
    def test_large_body_rejected(self):
        payload={'data':{'answer':'a'*20000,'status':'OBSERVED','requestId':'x','readOnly':True,'actionAuthorized':False}}
        c=JarvisBridge('https://vaos.example','x'*40,'spark-windows-1',opener=lambda *a,**k:Reply(payload))
        with self.assertRaises(JarvisBridgeError):c.ask('How many sales orders?')

    def test_rejects_contract_version_and_effects_ambiguity(self):
        """A remote status claim cannot override missing or contradictory safety evidence."""
        def open_with(data_overrides, drop=None):
            def send(request, timeout):
                identifier=json.loads(request.data)['requestId']
                reply={'schemaVersion':'SPARK_JARVIS_V1','requestId':identifier,
                       'readOnly':True,'actionAuthorized':False,
                       'businessEffectsExecuted':False,'status':'OBSERVED',
                       'answer':'2 stock records','sourceSystem':'VYNDI_OS',
                       'sourceAuthority':'getAuthoritativeInventory'}
                reply.update(data_overrides)
                if drop:
                    reply.pop(drop,None)
                return Reply({'data':reply})
            return send
        for bad,drop in [
            ({'businessEffectsExecuted':True},None),
            ({},'businessEffectsExecuted'),
            ({'schemaVersion':'SPARK_JARVIS_V2'},None),
            ({},'schemaVersion'),
        ]:
            with self.subTest(bad=bad,missing=drop):
                c=JarvisBridge('https://vaos.example','x'*40,'spark-windows-1',
                               opener=open_with(bad,drop))
                with self.assertRaises(JarvisBridgeError):
                    c.ask('How many stock items are recorded?')

if __name__=='__main__': unittest.main()
