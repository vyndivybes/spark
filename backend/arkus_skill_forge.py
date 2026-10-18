# Actual source port from user-owned vyndivybes/ARKUS/skill_forge.py
# Preserves ARKUS's validation, indexing and skill lifecycle behavior.
"""ARKUS Skill Forge: model-assisted, local-first declarative computation skills.

Skills contain validated JSON, never Python/JavaScript/shell commands.
No loading modules, files, network, subprocesses or OS automation.
"""
import json
import math
import os
import re
import secrets
import threading
from pathlib import Path


class SkillError(ValueError):
    pass


OPS={"add":2,"subtract":2,"multiply":2,"divide":2,"percentage":2,"average":2,"clamp":3}
MAX_SKILLS=40


def check_spec(spec):
    if not isinstance(spec,dict):
        raise SkillError("Skill must be a JSON object.")
    if set(spec)-{"name","description","operation","inputs","output","tests"}:
        raise SkillError("Skill contains unsupported fields. Executable code is not accepted.")
    name=spec.get("name")
    desc=spec.get("description")
    op=spec.get("operation")
    inputs=spec.get("inputs")
    if not isinstance(name,str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,31}",name):
        raise SkillError("Use an identifier of 2–32 lowercase letters, digits or underscores.")
    if not isinstance(desc,str) or not 1<=len(desc.strip())<=180:
        raise SkillError("Skill description required, up to 180 characters.")
    if op not in OPS:
        raise SkillError("Only built-in safe calculation operations are available.")
    if not isinstance(inputs,list) or len(inputs)!=OPS[op] or len(set(map(str,inputs)))!=len(inputs) or any(
        not isinstance(x,str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}",x) for x in inputs
    ):
        raise SkillError("Supply unique, valid variable names for the chosen operation.")
    output=spec.get("output","Result")
    if not isinstance(output,str) or len(output)>100:
        raise SkillError("Output label too long.")
    cases=spec.get("tests",[])
    if not isinstance(cases,list) or len(cases)>20:
        raise SkillError("Supply at most 20 independent expected-result examples.")
    for case in cases:
        if not isinstance(case,dict) or set(case)!={"parameters","expected"}:
            raise SkillError("Each example needs parameters and an expected result.")
        params=case["parameters"];expected=case["expected"]
        if (not isinstance(params,dict) or set(params)!=set(inputs)
                or any(type(v) not in (int,float) or abs(v)>1e12 or not math.isfinite(v) for v in params.values())
                or type(expected) not in (int,float) or abs(expected)>1e24 or not math.isfinite(expected)):
            raise SkillError("Examples must use the declared inputs and finite numeric results.")
    return {"name":name,"description":desc.strip(),"operation":op,"inputs":inputs,"output":output,"tests":cases}


def evaluate(spec,params):
    if not isinstance(params,dict) or set(params)!=set(spec["inputs"]):
        raise SkillError("Use precisely the declared numeric inputs.")
    values=[]
    for key in spec["inputs"]:
        val=params[key]
        if isinstance(val,bool):
            raise SkillError("Numeric values only.")
        try:
            number=float(val)
        except (ValueError,TypeError,OverflowError):
            raise SkillError("Numeric values only.") from None
        if not math.isfinite(number) or abs(number)>1e12:
            raise SkillError("Numbers must be finite and within range.")
        values.append(number)
    a,b=values[:2]
    op=spec["operation"]
    if op=="add": result=a+b
    elif op=="subtract": result=a-b
    elif op=="multiply": result=a*b
    elif op=="divide":
        if b==0: raise SkillError("Division by zero.")
        result=a/b
    elif op=="percentage": result=a*b/100
    elif op=="average": result=(a+b)/2
    else:
        lower,upper=values[1:]
        if lower>upper: raise SkillError("Clamp minimum exceeds maximum.")
        result=min(max(a,lower),upper)
    if not math.isfinite(result) or abs(result)>1e24:
        raise SkillError("Calculation exceeds safe limits.")
    return result


class SkillForge:
    def __init__(self,data_dir):
        self.root=Path(data_dir).resolve()/"skills"
        self.lock=threading.RLock()

    def _file(self,project):
        if not isinstance(project,str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*",project):
            raise SkillError("Invalid project identifier.")
        folder=self.root/project
        path=folder/"registry.json"
        if any(p.is_symlink() for p in (self.root,folder,path)):
            raise SkillError("Linked skill storage is prohibited.")
        if not folder.resolve().is_relative_to(self.root.resolve()):
            raise SkillError("Invalid project storage.")
        return path

    def _load(self,project):
        path=self._file(project)
        if not path.exists(): return []
        if path.stat().st_size>150000: raise SkillError("Skill registry too large.")
        try:
            result=json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(result,list) or len(result)>MAX_SKILLS: raise ValueError()
            for item in result:
                check_spec(item["spec"])
                if item["status"] not in ("draft","tested","active"): raise ValueError()
            return result
        except (OSError,ValueError,KeyError,TypeError) as exc:
            raise SkillError("Skill registry corrupt; unchanged.") from exc

    def _save(self,project,items):
        path=self._file(project)
        path.parent.mkdir(parents=True,exist_ok=True)
        scratch=path.with_name(path.name+"."+secrets.token_hex(5)+".tmp")
        try:
            encoded=json.dumps(items,indent=2)
            if len(encoded.encode("utf-8"))>150000:
                raise SkillError("Skill registry size limit reached; unchanged.")
            scratch.write_text(encoded,encoding="utf-8")
            os.replace(scratch,path)
        finally:
            scratch.unlink(missing_ok=True)

    def available(self,project):
        with self.lock:
            return [{"id":item["id"],"status":item["status"],"revision":item.get("revision",1),
                     "supersedes":item.get("supersedes"),**check_spec(item["spec"])} for item in self._load(project)]

    def propose(self,spec,project):
        spec=check_spec(spec)
        with self.lock:
            items=self._load(project)
            if len(items)>=MAX_SKILLS: raise SkillError("Maximum 40 skills per project.")
            if any(i["spec"]["name"]==spec["name"] for i in items):
                raise SkillError("A skill already exists with this name.")
            item={"id":secrets.token_hex(8),"status":"draft","spec":spec}
            items.append(item)
            self._save(project,items)
            return {"id":item["id"],"status":"draft",**spec}

    def _get(self,items,skill_id):
        item=next((i for i in items if i["id"]==skill_id),None)
        if item is None: raise SkillError("Skill not found in this project.")
        return item

    def revise(self,project,skill_id,spec):
        spec=check_spec(spec)
        if not spec["tests"]:
            raise SkillError("An upgrade requires independent expected-result examples.")
        with self.lock:
            items=self._load(project)
            base=self._get(items,skill_id)
            if base["status"]!="active":
                raise SkillError("Draft upgrades from the currently active revision.")
            if spec["name"]!=base["spec"]["name"] or spec["inputs"]!=base["spec"]["inputs"]:
                raise SkillError("Upgrades must retain the skill name and input interface.")
            if len(items)>=MAX_SKILLS:
                raise SkillError("Skill and revision limit reached.")
            item={"id":secrets.token_hex(8),"status":"draft","spec":spec,
                  "revision":base.get("revision",1)+1,"supersedes":base["id"]}
            items.append(item);self._save(project,items)
            return {"id":item["id"],"status":"draft","revision":item["revision"],**spec}

    @staticmethod
    def _check_tests(spec):
        spec=check_spec(spec)
        samples=[{name:float(index+2) for index,name in enumerate(spec["inputs"])},
                 {name:0.0 for name in spec["inputs"]}]
        for sample in samples:
            try:evaluate(spec,sample)
            except SkillError as exc:
                if "Division by zero" not in str(exc) and "Clamp minimum" not in str(exc):raise
        for index,case in enumerate(spec["tests"],1):
            actual=evaluate(spec,case["parameters"])
            if not math.isclose(actual,case["expected"],rel_tol=1e-9,abs_tol=1e-9):
                raise SkillError(f"Acceptance example {index} failed: expected {case['expected']}, got {actual}.")
        return len(spec["tests"])

    def test(self,project,skill_id):
        with self.lock:
            items=self._load(project);item=self._get(items,skill_id)
            count=self._check_tests(item["spec"])
            if item["status"]!="active":item["status"]="tested"
            self._save(project,items)
            return {"id":skill_id,"status":item["status"],
                    "tests":f"Built-in boundary checks and {count} expected-result examples passed."}

    def activate(self,project,skill_id):
        with self.lock:
            items=self._load(project);item=self._get(items,skill_id)
            if item["status"] not in ("tested","active"):
                raise SkillError("Skill must pass tests before activation.")
            current=next((i for i in items if i["spec"]["name"]==item["spec"]["name"] and i["status"]=="active"),None)
            if current and current["id"]!=skill_id and item.get("supersedes")!=current["id"]:
                raise SkillError("The active revision changed. Create a new upgrade or use rollback.")
            if item.get("supersedes") and current is None:
                raise SkillError("The original active skill is unavailable.")
            self._check_tests(item["spec"])
            if current and current["id"]!=skill_id:current["status"]="tested"
            item["status"]="active";self._save(project,items)
            return {"id":skill_id,"status":"active","name":item["spec"]["name"]}

    def rollback(self,project,skill_id):
        with self.lock:
            items=self._load(project);item=self._get(items,skill_id)
            if item["status"]!="active" or not item.get("supersedes"):
                raise SkillError("Only an active upgrade can roll back to its preceding revision.")
            previous=self._get(items,item["supersedes"])
            self._check_tests(previous["spec"])
            item["status"]="tested";previous["status"]="active"
            self._save(project,items)
            return {"id":previous["id"],"status":"active","name":previous["spec"]["name"]}

    def run(self,project,name,params):
        with self.lock:
            item=next((i for i in self._load(project)
                       if i["spec"]["name"]==name and i["status"]=="active"),None)
            if item is None: raise SkillError("No active skill with that name.")
            result=evaluate(item["spec"],params)
            return {"skill":name,"result":result,"output":item["spec"]["output"],
                    "execution":"local_allowlisted_math_only"}
