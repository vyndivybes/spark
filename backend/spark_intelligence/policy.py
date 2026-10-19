"""Small, offline policy components; these do not change live voice providers."""
import json
import re
import time
import uuid
from .runtime import Runtime, PolicyError


def parse_envelope(raw):
    """Strict action/final envelope, informed by OpenJarvis native_react.py.

    Never salvage an action from malformed model output or expose thought text.
    """
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key]=value
        return result
    def reject(value):
        raise ValueError('Invalid JSON constant')
    if not isinstance(raw,str) or len(raw)>32000:
        raise ValueError('Invalid model envelope')
    value=json.loads(raw,object_pairs_hook=unique,parse_constant=reject)
    if not isinstance(value,dict) or set(value)-{'thought','action','action_input','final'}:
        raise ValueError('Invalid model envelope fields')
    if 'action' in value and 'final' in value:
        raise ValueError('Action and final are mutually exclusive')
    if 'action' in value:
        if value['action'] not in Runtime.ACTIONS or not isinstance(value.get('action_input'),dict):
            raise ValueError('Action is outside approved scope')
        return {'action':value['action'],'action_input':value['action_input']}
    if not isinstance(value.get('final'),str) or not value['final'].strip():
        raise ValueError('A final answer or allowed action is required')
    return {'final':value['final']}


class Router:
    def __init__(self, providers):
        self.providers=providers

    def select(self, query, *, allow_cloud=False, preference=None, memory_limit_mb=None):
        if not isinstance(query,str) or not query or len(query)>100000:
            raise ValueError('Invalid task query')
        estimate=(len(query)+3)//4+512
        signals=sum(bool(re.search(pattern,query,re.I)) for pattern in (r'\b(prove|theorem|derive)\b',r'\b(algorithm|code|debug)\b',r'\b(step by step|analyze|compare)\b'))
        target=3 if signals>=2 or len(query)>4000 else 2 if signals else 1
        eligible=[p for p in self.providers if p.get('available') is True and (p.get('local') is True or allow_cloud is True) and p.get('context',0)>=estimate and (not preference or p.get('id')==preference) and (memory_limit_mb is None or not p.get('local') or p.get('additional_memory_mb',0)<=memory_limit_mb)]
        if not eligible:
            raise ValueError('No authorized available model fits the context; configure a local model or explicitly allow a cloud provider')
        chosen=min(eligible,key=lambda p:(not p.get('local'),abs(p.get('quality_tier',1)-target),p.get('latency_ms',float('inf'))))
        return {**chosen,'estimated_input_tokens':estimate-512,'token_measurement':'estimate','complexity_tier':target,'complexity_measurement':'heuristic; quality tiers and additional memory are host declarations','cost':None}


class CircuitBreaker:
    def __init__(self, *, clock=time.monotonic, threshold=3, cooldown=30):
        self.clock,self.threshold,self.cooldown=clock,threshold,cooldown
        self.failures=0
        self.opened=None
        self.last_failure=None

    def failure(self, classification):
        self.failures+=1
        self.last_failure=classification
        if self.failures>=self.threshold:
            self.opened=self.clock()

    def success(self):
        self.failures=0
        self.opened=None
        self.last_failure=None

    def allowed(self):
        return self.opened is None or self.clock()-self.opened>=self._delay()

    def _delay(self):
        return min(300,self.cooldown*2**min(4,max(0,self.failures-self.threshold)))

    def status(self):
        return {'state':'failed' if not self.allowed() else 'degraded' if self.failures else 'healthy','failures':self.failures,'last_failure':self.last_failure,'retry_after':max(0,self._delay()-(self.clock()-self.opened)) if self.opened is not None else 0}


class Improvements:
    """Versioned artifacts; evaluate accepts trusted benchmark-runner observations.

    Callers must execute their benchmarks independently. This API does not
    establish that a proposed prompt caused an improvement in a live model.
    """
    def __init__(self,directory):
        self.store=Runtime(directory,executor=None)

    def propose(self,project,content,kind):
        self.store._project(project)
        if len(self.store._list('improvement',project))>=200:raise ValueError('Project improvement registry limit reached')
        if kind not in ('prompt','few_shot','skill_description') or not isinstance(content,str) or not 1<=len(content)<=10000:
            raise ValueError('Invalid improvement artifact')
        value=dict(id=uuid.uuid4().hex,content=content,kind=kind,status='staged',created=time.time())
        return self.store._save('improvement',project,value['id'],value)

    def evaluate(self,project,identifier,cases):
        candidate=self.store._get('improvement',project,identifier)
        if candidate['status']!='staged' or not isinstance(cases,list) or not 1<=len(cases)<=100:
            raise ValueError('A staged candidate and bounded benchmark cases are required')
        if any(not isinstance(case,dict) or set(case)!={'expected','baseline','candidate'} for case in cases):
            raise ValueError('Invalid benchmark evidence')
        baseline=sum(case['baseline']==case['expected'] for case in cases)
        score=sum(case['candidate']==case['expected'] for case in cases)
        regression=any(case['baseline']==case['expected'] and case['candidate']!=case['expected'] for case in cases)
        candidate.update(status='rejected' if regression or score<baseline or score==0 else 'tested',evidence={'cases':len(cases),'baseline_correct':baseline,'candidate_correct':score,'regression':regression})
        return self.store._save('improvement',project,identifier,candidate)

    def activate(self,project,identifier,*,approved=False):
        candidate=self.store._get('improvement',project,identifier)
        if approved is not True or candidate['status']!='tested':
            raise ValueError('A tested candidate and explicit approval are required')
        previous=[item for item in self.store._list('improvement',project) if item['kind']==candidate['kind'] and item['status']=='active']
        candidate['supersedes']=previous[0]['id'] if previous else None
        for item in previous:
            item['status']='superseded'
            self.store._save('improvement',project,item['id'],item)
        candidate['status']='active'
        return self.store._save('improvement',project,identifier,candidate)

    def rollback(self,project,identifier,*,approved=False):
        candidate=self.store._get('improvement',project,identifier)
        if approved is not True or candidate['status']!='active':
            raise ValueError('Explicit rollback approval is required')
        if candidate.get('supersedes'):
            prior=self.store._get('improvement',project,candidate['supersedes'])
            prior['status']='active'
            self.store._save('improvement',project,prior['id'],prior)
        candidate['status']='rolled_back'
        return self.store._save('improvement',project,identifier,candidate)

    def close(self):
        self.store.close_storage()
