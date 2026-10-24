"""One bounded OpenRouter free-router request; never a paid fallback."""
import json
import os
from decimal import Decimal, InvalidOperation
import urllib.error
import urllib.request
from spark_rea_blueprint import BlueprintError, SCHEMA_PROMPT, validate_blueprint

MODEL='openrouter/free'
MODELS_URL='https://openrouter.ai/api/v1/models'
CHAT_URL='https://openrouter.ai/api/v1/chat/completions'

class FreeInferenceError(ValueError):pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None

def request_json(url,body=None,key=None):
    headers={'Content-Type':'application/json'}
    if key:headers['Authorization']='Bearer '+key
    data=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(url,data=data,headers=headers,method='POST' if data else 'GET')
    try:
        opener=urllib.request.build_opener(NoRedirect,urllib.request.ProxyHandler({}))
        with opener.open(req,timeout=45) as response:
            raw=response.read(8_000_001)
            if len(raw)>8_000_000:raise FreeInferenceError('Provider response exceeds its bound.')
            return json.loads(raw)
    except (urllib.error.URLError,OSError,ValueError):
        raise FreeInferenceError('Free route unavailable, rate limited, or invalid. No retry or paid fallback was attempted.') from None

def qualify_catalog(catalog):
    entries=catalog.get('data') if isinstance(catalog,dict) else None
    if not isinstance(entries,list):raise FreeInferenceError('Free-route catalog unavailable.')
    rows=[r for r in entries if isinstance(r,dict) and r.get('id')==MODEL]
    if len(rows)!=1:raise FreeInferenceError('The exact free router is unavailable.')
    pricing=rows[0].get('pricing',{})
    try:
        if any(Decimal(str(pricing[k]))!=0 for k in ('prompt','completion')) or Decimal(str(pricing.get('request','0')))!=0:
            raise FreeInferenceError('Route price is not verified zero. Generation blocked.')
    except (KeyError,InvalidOperation,TypeError):raise FreeInferenceError('Free-route pricing is incomplete.') from None
    return {'model':MODEL,'prompt_price':'0','completion_price':'0','request_price':'0','source':MODELS_URL}

class FreeBlueprintGenerator:
    def __init__(self,transport=None,key=None):
        self.transport=transport or request_json
        self.key=key
    def status(self):
        return {'model':MODEL,'key_configured':bool(self.key or os.environ.get('OPENROUTER_API_KEY')),
                'policy':'catalog-verified zero pricing; one request; no retries or paid fallback',
                'live_qualification':'checked only when generation is explicitly requested'}
    def generate(self,report,goal,consent):
        if consent is not True:raise FreeInferenceError('Approve sharing the displayed sanitized report excerpt and goal with the free model first.')
        if not isinstance(goal,str) or not 10<=len(goal.strip())<=1200:raise FreeInferenceError('Describe the original app in 10-1200 characters.')
        key=self.key or os.environ.get('OPENROUTER_API_KEY')
        if not key:raise FreeInferenceError('OPENROUTER_API_KEY is not configured. Supply a blueprint directly or configure the existing free router; no inference was sent.')
        qualification=qualify_catalog(self.transport(MODELS_URL))
        evidence='\n'.join(section['title']+'\n'+section['text'] for section in report['sections'])[:6000]
        body={'model':MODEL,'stream':False,'temperature':0,'max_tokens':3500,
              'response_format':{'type':'json_object'},'messages':[{'role':'system','content':SCHEMA_PROMPT},
              {'role':'user','content':json.dumps({'goal':goal.strip(),'untrusted_report_excerpt':evidence})}]}
        result=self.transport(CHAT_URL,body=body,key=key)
        try:
            choice=result['choices'][0]
            if choice.get('finish_reason')!='stop':raise FreeInferenceError('Free model did not finish; no blueprint saved.')
            usage=result.get('usage') or {}
            if 'cost' in usage and Decimal(str(usage['cost']))!=0:raise FreeInferenceError('Provider reported a nonzero cost; response refused.')
            blueprint=validate_blueprint(json.loads(choice['message']['content']))
        except (KeyError,IndexError,TypeError,ValueError,InvalidOperation) as error:
            if isinstance(error,FreeInferenceError):raise
            raise FreeInferenceError('The free model returned an invalid blueprint. No app was built.') from None
        return {'blueprint':blueprint,'qualification':qualification,'returned_model':str(result.get('model','unknown'))[:160],'inference':'OpenRouter free router; one explicit request'}
