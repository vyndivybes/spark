"""Persistent original Python-expression skills; bounded interpreter, no Python eval/exec.

A skill is one `def run(inputs)` function with local assignments/conditionals. Supported data
expressions/comprehensions are evaluated under a step budget in a fresh process.
There are no imports, attributes, files, network, or arbitrary Python statements.
"""
import ast
import hashlib
import json
import math
import operator
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading


class CodeSkillError(ValueError):
    pass


LIMIT = 32000


def bounded(value):
    try:
        raw = json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, OverflowError):
        raise CodeSkillError('Only finite JSON data is supported.') from None
    if len(raw.encode()) > LIMIT:
        raise CodeSkillError('Skill data exceeds 32 KB.')
    return value


def parse_source(source):
    if not isinstance(source, str) or not 1 <= len(source.encode()) <= 8000:
        raise CodeSkillError('Skill code must be 1–8000 bytes.')
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        raise CodeSkillError('Invalid skill Python syntax.') from None
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise CodeSkillError('Define exactly one function: def run(inputs).')
    fn = tree.body[0]
    if (fn.name != 'run' or fn.decorator_list or fn.type_comment or
        fn.args.posonlyargs or fn.args.kwonlyargs or fn.args.vararg or fn.args.kwarg or
        fn.args.defaults or len(fn.args.args) != 1 or fn.args.args[0].arg != 'inputs' or
        not fn.body):
        raise CodeSkillError('Use one pure def run(inputs) function.')
    def statements(body):
        for statement in body:
            if isinstance(statement,ast.Assign):
                if len(statement.targets)!=1 or not isinstance(statement.targets[0],ast.Name):raise CodeSkillError('Assign only local names.')
            elif isinstance(statement,ast.If):statements(statement.body);statements(statement.orelse)
            elif isinstance(statement,ast.Return):pass
            elif isinstance(statement,ast.Expr) and isinstance(statement.value,ast.Constant) and isinstance(statement.value.value,str):pass
            else:raise CodeSkillError('Use local assignments, if statements and returns only.')
    statements(fn.body)
    allowed = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign, ast.If, ast.Expr,
               ast.Constant, ast.Name, ast.Load, ast.Store, ast.BinOp, ast.UnaryOp,
               ast.BoolOp, ast.Compare, ast.IfExp, ast.Subscript, ast.Slice,
               ast.List, ast.Tuple, ast.Dict, ast.ListComp, ast.GeneratorExp, ast.comprehension,
               ast.Call, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
               ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq,
               ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot)
    nodes = list(ast.walk(tree))
    if len(nodes) > 600 or any(not isinstance(n, allowed) for n in nodes):
        unsupported=next((type(n).__name__ for n in nodes if not isinstance(n,allowed)),'complexity limit')
        raise CodeSkillError('Unsupported Python operation: '+unsupported)
    for node in nodes:
        if isinstance(node, ast.Name) and (node.id.startswith('_') or len(node.id)>40):
            raise CodeSkillError('Private names are unavailable.')
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords):
            raise CodeSkillError('Call only the documented pure helper functions.')
        if isinstance(node, ast.comprehension) and (node.is_async or not isinstance(node.target, ast.Name)):
            raise CodeSkillError('Comprehensions need a simple local variable.')
    return fn.body


def split(value, separator=None):
    return str(value).split(separator)[:1000]


def join(separator, values):
    if len(values)>1000: raise CodeSkillError('Too many values.')
    return str(separator).join(str(v) for v in values)


FUNCTIONS = {'len':len, 'sum':sum, 'min':min, 'max':max, 'round':round,
             'abs':abs, 'sorted':sorted, 'all':all, 'any':any, 'str':str,
             'int':int, 'float':float, 'split':split, 'join':join,
             'lower':lambda x:str(x).lower(), 'upper':lambda x:str(x).upper()}
BINARY = {ast.Add:operator.add, ast.Sub:operator.sub, ast.Mult:operator.mul,
          ast.Div:operator.truediv, ast.FloorDiv:operator.floordiv, ast.Mod:operator.mod}
COMPARE = {ast.Eq:operator.eq, ast.NotEq:operator.ne, ast.Lt:operator.lt,
           ast.LtE:operator.le, ast.Gt:operator.gt, ast.GtE:operator.ge,
           ast.In:lambda a,b:a in b, ast.NotIn:lambda a,b:a not in b, ast.Is:operator.is_, ast.IsNot:operator.is_not}


def evaluate(source, inputs):
    statements = parse_source(source)
    bounded(inputs)
    remaining = [10000]
    def visit(node, scope, depth=0):
        remaining[0] -= 1
        if remaining[0]<0 or depth>80: raise CodeSkillError('Skill computation budget exceeded.')
        go=lambda n:visit(n,scope,depth+1)
        if isinstance(node, ast.Constant): result=node.value
        elif isinstance(node, ast.Name): result=scope[node.id]
        elif isinstance(node, (ast.List,ast.Tuple)): result=[go(n) for n in node.elts]
        elif isinstance(node, ast.Dict): result={go(k):go(v) for k,v in zip(node.keys,node.values)}
        elif isinstance(node, ast.Subscript): result=go(node.value)[go(node.slice)]
        elif isinstance(node, ast.Slice): return slice(go(node.lower) if node.lower else None,go(node.upper) if node.upper else None,go(node.step) if node.step else None)
        elif isinstance(node, ast.IfExp): result=go(node.body if go(node.test) else node.orelse)
        elif isinstance(node, ast.UnaryOp):
            val=go(node.operand); result=not val if isinstance(node.op,ast.Not) else -val if isinstance(node.op,ast.USub) else +val
        elif isinstance(node, ast.BoolOp):
            result=go(node.values[0])
            for value in node.values[1:]:
                if isinstance(node.op,ast.And) and not result: break
                if isinstance(node.op,ast.Or) and result: break
                result=go(value)
        elif isinstance(node, ast.BinOp):
            a,b=go(node.left),go(node.right)
            if isinstance(node.op,ast.Mult):
                seq,count=(a,b) if isinstance(a,(str,list)) else (b,a)
                if isinstance(seq,(str,list)) and (not isinstance(count,int) or len(seq)*max(0,count)>LIMIT):
                    raise CodeSkillError('Repeated sequence exceeds budget.')
            if isinstance(node.op,ast.Mod) and isinstance(a,str): raise CodeSkillError('String formatting is unavailable.')
            result=BINARY[type(node.op)](a,b)
        elif isinstance(node, ast.Compare):
            a=go(node.left);result=True
            for op,other in zip(node.ops,node.comparators):
                b=go(other)
                if not COMPARE[type(op)](a,b): result=False;break
                a=b
        elif isinstance(node, ast.Call): result=FUNCTIONS[node.func.id](*[go(a) for a in node.args])
        elif isinstance(node, (ast.ListComp,ast.GeneratorExp)):
            result=[]
            def collect(index, local):
                if index==len(node.generators):
                    result.append(visit(node.elt,local,depth+1))
                    if len(result)>1000: raise CodeSkillError('Too many result items.')
                    return
                gen=node.generators[index]; values=visit(gen.iter,local,depth+1)
                if not isinstance(values,(list,str,dict)) or len(values)>1000: raise CodeSkillError('Comprehension input exceeds budget.')
                for value in values:
                    child={**local,gen.target.id:value}
                    if all(visit(test,child,depth+1) for test in gen.ifs): collect(index+1,child)
            collect(0,scope)
        else: raise CodeSkillError('Unsupported expression.')
        return bounded(result)
    try:
        scope={'inputs':inputs}
        def run_body(body):
            for statement in body:
                remaining[0]-=1
                if remaining[0]<0:raise CodeSkillError('Skill computation budget exceeded.')
                if isinstance(statement,ast.Assign):scope[statement.targets[0].id]=visit(statement.value,scope)
                elif isinstance(statement,ast.Return):return True,visit(statement.value,scope) if statement.value else None
                elif isinstance(statement,ast.If):
                    returned,value=run_body(statement.body if visit(statement.test,scope) else statement.orelse)
                    if returned:return True,value
            return False,None
        returned,result=run_body(statements)
        if not returned:raise CodeSkillError('Skill did not return a result.')
        return result
    except (KeyError, TypeError, ValueError, ArithmeticError, IndexError, RecursionError) as exc:
        raise CodeSkillError(str(exc)[:180]) from None


def execute(source, inputs):
    parse_source(source);bounded(inputs)
    try:
        process=subprocess.run([sys.executable,'-I','-S',str(Path(__file__).resolve()),'--worker'],
            input=json.dumps({'source':source,'inputs':inputs}),text=True,capture_output=True,
            timeout=4,cwd=str(Path(__file__).resolve().parent),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
            env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP'}})
        if process.returncode: raise CodeSkillError('Skill worker failed.')
        result=json.loads(process.stdout)
        if not result.get('ok'): raise CodeSkillError(result.get('error','Skill execution failed.'))
        return bounded(result['result'])
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        raise CodeSkillError('Skill worker failed or exceeded four seconds.') from None


class CodeSkills:
    def __init__(self, root):
        self.root=Path(root)/'code-skills';self.lock=threading.RLock()
    def _path(self, project):
        if not isinstance(project,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}',project): raise CodeSkillError('Invalid project.')
        path=self.root/(project+'.json')
        if path.is_symlink() or self.root.is_symlink(): raise CodeSkillError('Linked skill storage prohibited.')
        return path
    def _read(self,project):
        path=self._path(project)
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    def _save(self,project,rows):
        from spark_maintenance import atomic_write
        atomic_write(self._path(project),json.dumps(rows,ensure_ascii=False).encode())
    def list(self,project):
        with self.lock:return self._read(project)
    def propose(self,project,spec,provenance=None):
        if not isinstance(spec,dict) or set(spec)!={'name','description','source','tests'}:raise CodeSkillError('Invalid code skill fields.')
        if not isinstance(spec['name'],str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,31}',spec['name']):raise CodeSkillError('Invalid skill name.')
        if not isinstance(spec['description'],str) or not 1<=len(spec['description'])<=300:raise CodeSkillError('Describe the skill in up to 300 characters.')
        parse_source(spec['source'])
        tests=spec['tests']
        if not isinstance(tests,list) or not 2<=len(tests)<=12 or any(not isinstance(t,dict) or set(t)!={'inputs','expected'} for t in tests):raise CodeSkillError('Provide 2–12 input/expected examples.')
        bounded(tests)
        if len({json.dumps(t['inputs'],sort_keys=True) for t in tests})<2:raise CodeSkillError('Use distinct test inputs.')
        from spark_security_scan import scan_secrets
        if scan_secrets(json.dumps(spec),'generated_skill'):raise CodeSkillError('Possible secret in generated skill.')
        with self.lock:
            rows=self._read(project)
            if len(rows)>=80:raise CodeSkillError('Project code skill limit reached.')
            record={**spec,'id':secrets.token_hex(12),'status':'proposed','sha256':hashlib.sha256(spec['source'].encode()).hexdigest(),'provenance':provenance or {}}
            rows.append(record);self._save(project,rows);return record
    def action(self,project,action,identity,*,approved=False,inputs=None):
        with self.lock:
            rows=self._read(project);record=next((r for r in rows if r['id']==identity),None)
            if record is None:raise CodeSkillError('Unknown code skill revision.')
            if hashlib.sha256(record['source'].encode()).hexdigest()!=record.get('sha256'):
                raise CodeSkillError('Skill integrity changed; propose and test a new revision.')
            if action=='test':
                results=[]
                for case in record['tests']:
                    try: results.append({'passed':execute(record['source'],case['inputs'])==case['expected']})
                    except CodeSkillError as exc:results.append({'passed':False,'error':str(exc)})
                record['test_results']=results
                # A failed re-test must not leave the revision executable.
                record['status']='tested' if all(r['passed'] for r in results) else 'rejected'
            elif action=='activate':
                if approved is not True or record['status']!='tested':raise CodeSkillError('Review and approve a tested revision first.')
                # Re-test at activation, so stored status alone never authorizes execution.
                if any(execute(record['source'],c['inputs'])!=c['expected'] for c in record['tests']):raise CodeSkillError('Activation test failed.')
                for other in rows:
                    if other['name']==record['name'] and other['status']=='active':other['status']='inactive'
                record['status']='active'
            elif action=='run':
                if record['status']!='active':raise CodeSkillError('Activate this tested skill before running it.')
                return {'id':identity,'result':execute(record['source'],inputs)}
            elif action=='deactivate':record['status']='inactive'
            else:raise CodeSkillError('Unknown skill operation.')
            self._save(project,rows);return record


if __name__=='__main__' and sys.argv[1:]==['--worker']:
    try:
        request=json.loads(sys.stdin.read(48000))
        print(json.dumps({'ok':True,'result':evaluate(request['source'],request['inputs'])},allow_nan=False))
    except Exception as exc:
        print(json.dumps({'ok':False,'error':str(exc)[:180]}))
