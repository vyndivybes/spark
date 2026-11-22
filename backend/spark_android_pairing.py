"""Ephemeral Android pairing approval registry (not a network transport).

Pairing grants no device commands. Caller must enforce local owner authentication
and a TLS/Noise authenticated encrypted transport independently.
"""
import hashlib
import hmac
import re
import secrets
import threading
import time

_KEY = re.compile(r"[A-Za-z0-9_-]{43,128}\Z")

class PairingError(ValueError):
    pass

class PairingRegistry:
    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.lock = threading.RLock()
        self.pending = {}
        self.devices = {}

    @staticmethod
    def _digest(value):
        return hashlib.sha256(value.encode("ascii")).hexdigest()

    def _purge(self):
        now=self.clock()
        for key,item in list(self.pending.items()):
            if item["expires_at"] <= now:
                del self.pending[key]

    def begin(self, *, owner_authenticated=False):
        if owner_authenticated is not True:
            raise PairingError("Authenticated desktop approval required.")
        with self.lock:
            self._purge()
            if len(self.pending) >= 3:
                raise PairingError("Too many outstanding pairing requests.")
            token=secrets.token_urlsafe(32)
            code=secrets.token_hex(3).upper()
            identity=self._digest(token)
            self.pending[identity]={"code":code,"expires_at":self.clock()+120,
                                    "candidate":None,"approved":False}
            return {"pairing_token":token,"verification_code":code,"expires_in_seconds":120,
                    "transport_ready":False}

    def request(self, token, public_key, device_name):
        if not isinstance(token,str) or not _KEY.fullmatch(token):
            raise PairingError("Invalid pairing token.")
        if not isinstance(public_key,str) or not _KEY.fullmatch(public_key):
            raise PairingError("Invalid public-key encoding.")
        if not isinstance(device_name,str) or not 1<=len(device_name.strip())<=60 or any(ord(c)<32 for c in device_name):
            raise PairingError("Invalid device name.")
        with self.lock:
            self._purge()
            item=self.pending.get(self._digest(token))
            if item is None or item["candidate"] is not None:
                raise PairingError("Pairing request expired, unknown or already claimed.")
            fingerprint=self._digest(public_key)
            item["candidate"]={"fingerprint":fingerprint,"name":device_name.strip()}
            return {"verification_code":item["code"],"fingerprint":fingerprint,
                    "owner_approval_required":True,"connected":False}

    def approve(self, token, verification_code, *, owner_authenticated=False):
        if owner_authenticated is not True:
            raise PairingError("Desktop owner approval required.")
        if not isinstance(token,str):
            raise PairingError("Invalid pairing token.")
        with self.lock:
            self._purge()
            identity=self._digest(token)
            item=self.pending.get(identity)
            if item is None or item["candidate"] is None or not isinstance(verification_code,str) or not hmac.compare_digest(item["code"],verification_code):
                raise PairingError("Pairing approval rejected.")
            candidate=item["candidate"]
            self.devices[candidate["fingerprint"]]={"name":candidate["name"],
                                                       "approved_at":self.clock()}
            del self.pending[identity]
            return {"approved":True,"device_fingerprint":candidate["fingerprint"],
                    "transport_ready":False,"permissions":[]}

    def revoke(self, fingerprint, *, owner_authenticated=False):
        if owner_authenticated is not True:
            raise PairingError("Desktop owner approval required.")
        with self.lock:
            return {"revoked":self.devices.pop(fingerprint,None) is not None}

    def list_devices(self, *, owner_authenticated=False):
        if owner_authenticated is not True:
            raise PairingError("Desktop owner authentication required.")
        with self.lock:
            return [{"fingerprint":k,"name":v["name"],"approved_at":v["approved_at"],
                     "permissions":[]} for k,v in sorted(self.devices.items())]
