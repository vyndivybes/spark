"""Outbound-only, read-only SPARK to VAOS Jarvis bridge.

Credentials stay in the local Python process, never in Electron/renderer.
Does not follow redirects, execute desktop instructions, or automatically retry actions.
"""
import json
import os
import re
import uuid
import hmac
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

DEVICE=re.compile(r"^[a-z][a-z0-9-]{3,63}$")
WRITE=re.compile(r"\b(approve|reject|execute|delete|transfer|dispatch|submit|authorize|authorise|activate|deactivate|override|merge|deploy|issue|write|pay|purchase|send|remove|update|modify|create)\b",re.I)
ALLOWED_STATUS=frozenset({'READY','HOLD','OBSERVED','UNAVAILABLE'})
MAX_REPLY=16384

class JarvisBridgeError(ValueError):
    pass

def local_bridge_client_allowed(environ, provided, expected):
    """No unauthenticated localhost or idle-voice fallback for VAOS delegation."""
    origin=(environ or {}).get('HTTP_ORIGIN','')
    return bool(origin in ('http://localhost:5173','http://127.0.0.1:5173')
                and isinstance(expected,str) and len(expected)==64
                and isinstance(provided,str) and len(provided)==64
                and hmac.compare_digest(provided,expected))

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None

def _real_open(request,timeout):
    return build_opener(_NoRedirect()).open(request,timeout=timeout)

class JarvisBridge:
    def __init__(self,endpoint,token,device_id,*,opener=None):
        if not isinstance(endpoint,str):
            raise JarvisBridgeError('Jarvis HTTPS endpoint is not configured.')
        try: parsed=urlsplit(endpoint)
        except ValueError: raise JarvisBridgeError('Jarvis HTTPS endpoint invalid.') from None
        if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ('','/') or parsed.query or parsed.fragment or not parsed.netloc):
            raise JarvisBridgeError('Jarvis requires a dedicated HTTPS origin.')
        if not isinstance(token,str) or not 32<=len(token)<=200 or any(c.isspace() for c in token):
            raise JarvisBridgeError('Jarvis device credential is not configured.')
        if not isinstance(device_id,str) or not DEVICE.fullmatch(device_id):
            raise JarvisBridgeError('Jarvis paired device identity is invalid.')
        self.url=endpoint.rstrip('/')+'/api/spark-bridge'
        self.token=token
        self.device_id=device_id
        self.open=opener or _real_open

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get('SPARK_JARVIS_URL',''),
                   os.environ.get('SPARK_JARVIS_TOKEN',''),
                   os.environ.get('SPARK_JARVIS_DEVICE_ID',''))

    def ask(self,question):
        if (not isinstance(question,str) or not 5<=len(question)<=300
                or any(ord(c)<32 or ord(c)==127 for c in question)):
            raise JarvisBridgeError('Use a single read-only question of 5–300 characters.')
        if WRITE.search(question):
            raise JarvisBridgeError('Jarvis bridge permits observation, not instructions or writes.')
        request_id=str(uuid.uuid4())
        payload={'version':1,'requestId':request_id,'deviceId':self.device_id,
                 'operation':'ask','question':question}
        request=Request(self.url,data=json.dumps(payload).encode('utf-8'),
                        method='POST',headers={'Authorization':'Bearer '+self.token,
                        'Content-Type':'application/json','Accept':'application/json'})
        try:
            with self.open(request,timeout=8) as response:
                if response.status!=200:
                    raise JarvisBridgeError('VAOS Jarvis source is unavailable.')
                raw=response.read(MAX_REPLY+1)
            if len(raw)>MAX_REPLY:
                raise JarvisBridgeError('Jarvis reply exceeds the safe limit.')
            data=json.loads(raw.decode('utf-8'))['data']
        except (HTTPError,URLError,TimeoutError,OSError,ValueError,KeyError,TypeError,UnicodeError) as error:
            if isinstance(error,JarvisBridgeError): raise
            raise JarvisBridgeError('Jarvis connection unavailable or response unverified.') from None
        if (not isinstance(data,dict) or data.get('requestId')!=request_id
                or data.get('schemaVersion')!='SPARK_JARVIS_V1'
                or data.get('readOnly') is not True or data.get('actionAuthorized') is not False
                or data.get('businessEffectsExecuted') is not False
                or data.get('status') not in ALLOWED_STATUS
                or not isinstance(data.get('answer'),str) or len(data['answer'])>1300):
            raise JarvisBridgeError('Jarvis response failed read-only verification.')
        # Only explicitly listed display fields can reach the desktop renderer.
        allowed=('status','answer','sourceAuthority','sourceSystem','recordsObserved',
                 'observedAt','sourceWindow','dataCompleteness','diagnosticCode')
        return {k:data[k] for k in allowed if k in data}
