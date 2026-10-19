"""Host-configured task inference, separate from established live voice sessions."""
import json
import asyncio
import os
import re
import time
from urllib.parse import urlsplit
from .policy import CircuitBreaker, Router


class Models:
    def __init__(self,config=None):
        self.config=config
        self.health={}
        self.breakers={}
        self.history=[]
        self.request_lock=asyncio.Lock()

    def _config(self):
        try:
            config=self.config if self.config is not None else json.loads(os.environ.get('SPARK_TASK_MODELS','{}'))
            if not isinstance(config,dict) or len(config)>8:
                raise ValueError()
            for identifier,item in config.items():
                if not isinstance(identifier,str) or not re.fullmatch(r'[a-z0-9-]{1,40}',identifier) or not isinstance(item,dict) or set(item)-{'provider','model','base_url','context','api_key_env','quality_tier','additional_memory_mb'}:
                    raise ValueError()
                if item.get('provider') not in ('ollama','openai_local','groq','gemini') or not isinstance(item.get('model'),str) or not re.fullmatch(r'[A-Za-z0-9_:.\-/]{1,150}',item['model']):
                    raise ValueError()
                if type(item.get('context')) is not int or not 1024<=item['context']<=2000000:
                    raise ValueError()
                if type(item.get('quality_tier',1)) is not int or item.get('quality_tier',1) not in (1,2,3) or type(item.get('additional_memory_mb',0)) is not int or not 0<=item.get('additional_memory_mb',0)<=262144:raise ValueError()
                if item['provider'] in ('ollama','openai_local'):
                    url=urlsplit(item.get('base_url',''))
                    if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost','::1') or url.username or url.password or url.query or url.fragment:
                        raise ValueError()
                if item.get('api_key_env') and not re.fullmatch(r'[A-Z][A-Z0-9_]{1,80}',item['api_key_env']):
                    raise ValueError()
            return config
        except (ValueError,TypeError):
            raise ValueError('Invalid host SPARK_TASK_MODELS configuration') from None

    def catalog(self):
        return [dict(id=identifier,provider=item['provider'],model=item['model'],context=item['context'],quality_tier=item.get('quality_tier',1),additional_memory_mb=item.get('additional_memory_mb',0),local=item['provider'] in ('ollama','openai_local'),**self.health.get(identifier,{'available':False,'state':'unprobed'})) for identifier,item in self._config().items()]

    def route(self,query,*,allow_cloud=False,cloud_provider=None):
        providers=[provider for provider in self.catalog() if provider['local'] or provider['id']==cloud_provider]
        try:
            import psutil
            budget=int(psutil.virtual_memory().available/1024/1024)
        except ImportError:budget=1024
        return Router(providers).select(query,allow_cloud=allow_cloud,memory_limit_mb=budget)

    def _endpoint(self,item):
        provider=item['provider']
        if provider=='groq':return 'https://api.groq.com/openai/v1'
        if provider=='gemini':return 'https://generativelanguage.googleapis.com/v1beta'
        return item['base_url'].rstrip('/')

    def _headers(self,item):
        env=item.get('api_key_env') or {'groq':'GROQ_API_KEY','gemini':'GEMINI_API_KEY'}.get(item['provider'])
        key=os.environ.get(env,'') if env else ''
        if item['provider'] in ('groq','gemini') and not key:
            raise ValueError('Provider credential is not configured on the host')
        return {'x-goog-api-key':key} if item['provider']=='gemini' else {'Authorization':'Bearer '+key} if key else {}

    async def _request(self,identifier,path,body=None):
        if self.request_lock.locked():raise ValueError('A task model request is already running; wait for its result')
        async with self.request_lock:
            return await self._perform_request(identifier,path,body)

    async def _perform_request(self,identifier,path,body=None):
        import httpx
        config=self._config()
        if identifier not in config:
            raise ValueError('Select a host-configured task model')
        item=config[identifier]
        breaker=self.breakers.setdefault(identifier,CircuitBreaker())
        if not breaker.allowed():
            raise ValueError('Model circuit is open; wait for cooldown before probing again')
        try:
            async with httpx.AsyncClient(timeout=20,trust_env=False,follow_redirects=False) as client:
                response=await client.request('POST' if body is not None else 'GET',self._endpoint(item)+path,json=body,headers=self._headers(item))
                response.raise_for_status()
                if len(response.content)>2000000:
                    raise ValueError('Model response exceeds limit')
                value=response.json()
                breaker.success()
                return value
        except Exception as error:
            limited=isinstance(error,httpx.HTTPStatusError) and error.response.status_code==429
            classification='rate_limited' if limited else 'provider_unavailable'
            breaker.failure(classification)
            self.health[identifier]={'available':False,'state':classification}
            raise ValueError('Model unavailable; check its service, model, credentials or quota. No fallback attempted.') from None

    async def probe(self,identifier,*,allow_cloud=False):
        config=self._config()
        if identifier not in config:raise ValueError('Unknown model')
        item=config[identifier]
        if item['provider'] in ('groq','gemini') and allow_cloud is not True:
            raise ValueError('Explicit cloud probe consent is required')
        started=time.perf_counter()
        try:
            data=await self._request(identifier,'/api/tags' if item['provider']=='ollama' else '/models')
            names=[model.get('name') if item['provider']=='ollama' else model.get('name','').removeprefix('models/') if item['provider']=='gemini' else model.get('id') for model in data.get('models',data.get('data',[]))]
            available=item['model'] in names
            status={'available':available,'state':'healthy' if available else 'model_not_installed','latency_ms':round((time.perf_counter()-started)*1000)}
        except ValueError:
            status={'available':False,'state':'unavailable','latency_ms':round((time.perf_counter()-started)*1000)}
        self.health[identifier]=status
        return status

    async def generate(self,identifier,query,*,allow_cloud=False):
        started=time.perf_counter()
        entry={'model_id':identifier,'ok':False,'input_tokens':None,'output_tokens':None,'cost':None,'ttft_seconds':None}
        try:
            Router(self.catalog()).select(query,allow_cloud=allow_cloud,preference=identifier)
            item=self._config()[identifier]
            provider=item['provider']
            if provider=='ollama':
                data=await self._request(identifier,'/api/generate',{'model':item['model'],'prompt':query,'stream':False,'keep_alive':0,'options':{'num_predict':512}})
                answer=data['response'];input_tokens=data.get('prompt_eval_count');output_tokens=data.get('eval_count')
            elif provider=='gemini':
                data=await self._request(identifier,'/models/'+item['model']+':generateContent',{'contents':[{'parts':[{'text':query}]}],'generationConfig':{'maxOutputTokens':512}})
                answer=''.join(part.get('text','') for part in data['candidates'][0]['content']['parts'])
                usage=data.get('usageMetadata',{});input_tokens=usage.get('promptTokenCount');output_tokens=usage.get('candidatesTokenCount')
            else:
                data=await self._request(identifier,'/chat/completions',{'model':item['model'],'messages':[{'role':'user','content':query}],'max_tokens':512})
                answer=data['choices'][0]['message']['content'];usage=data.get('usage',{});input_tokens=usage.get('prompt_tokens');output_tokens=usage.get('completion_tokens')
            if not isinstance(answer,str) or len(answer)>32000:raise ValueError('Invalid model answer')
            input_tokens=input_tokens if type(input_tokens) is int and 0<=input_tokens<=10000000 else None
            output_tokens=output_tokens if type(output_tokens) is int and 0<=output_tokens<=10000000 else None
            entry.update(ok=True,input_tokens=input_tokens,output_tokens=output_tokens)
            return {'answer':answer,'model_id':identifier,'usage':{'input_tokens':input_tokens,'output_tokens':output_tokens,'cost':None},'verified':False}
        except (KeyError,TypeError,IndexError):
            raise ValueError('Provider returned an invalid response') from None
        finally:
            entry['elapsed_seconds']=time.perf_counter()-started
            self.history.append(entry)
            self.history=self.history[-200:]
