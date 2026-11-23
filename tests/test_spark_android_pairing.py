import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from spark_android_pairing import PairingError,PairingRegistry

KEY="A"*43
class PairingTests(unittest.TestCase):
    def setUp(self):
        self.now=[20]
        self.p=PairingRegistry(clock=lambda:self.now[0])
    def test_explicit_owner_approval_and_revocation(self):
        with self.assertRaises(PairingError):self.p.begin()
        invite=self.p.begin(owner_authenticated=True)
        claim=self.p.request(invite["pairing_token"],KEY,"My phone")
        self.assertFalse(claim["connected"])
        with self.assertRaises(PairingError):
            self.p.approve(invite["pairing_token"],"BAD",owner_authenticated=True)
        with self.assertRaises(PairingError):
            self.p.approve(invite["pairing_token"],invite["verification_code"])
        approved=self.p.approve(invite["pairing_token"],invite["verification_code"],owner_authenticated=True)
        self.assertEqual(approved["permissions"],[])
        self.assertFalse(approved["transport_ready"])
        self.assertEqual(len(self.p.list_devices(owner_authenticated=True)),1)
        self.assertTrue(self.p.revoke(approved["device_fingerprint"],owner_authenticated=True)["revoked"])
    def test_expiration_and_replay(self):
        invite=self.p.begin(owner_authenticated=True)
        self.now[0]+=121
        with self.assertRaises(PairingError):self.p.request(invite["pairing_token"],KEY,"Phone")
        invite=self.p.begin(owner_authenticated=True)
        self.p.request(invite["pairing_token"],KEY,"Phone")
        with self.assertRaises(PairingError):self.p.request(invite["pairing_token"],KEY,"Phone")
        self.p.approve(invite["pairing_token"],invite["verification_code"],owner_authenticated=True)
        with self.assertRaises(PairingError):self.p.approve(invite["pairing_token"],invite["verification_code"],owner_authenticated=True)
    def test_invalid_data(self):
        i=self.p.begin(owner_authenticated=True)
        for args in (("oops",KEY,"Phone"),(i["pairing_token"],"broken","Phone"),(i["pairing_token"],KEY,"")):
            with self.assertRaises(PairingError):self.p.request(*args)
    def test_no_device_command_permissions(self):
        invite=self.p.begin(owner_authenticated=True)
        self.assertFalse(invite["transport_ready"])
        self.assertEqual(self.p.list_devices(owner_authenticated=True),[])

if __name__=="__main__":
    unittest.main()
