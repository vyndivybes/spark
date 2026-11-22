"""Voice-first adapter for SPARK's already sandboxed code-skill lifecycle.

Never execute arbitrary speech as Python. Preparation invokes the existing
generated-code restrictions, tests the resulting candidate, and leaves it inactive.
Activation requires an explicit second utterance and existing test gate.
"""
import re

NAME=r"[a-z][a-z0-9_]{1,31}"

def parse_skill_voice(text):
    if not isinstance(text,str) or len(text)>600:
        return None
    text=text.strip().rstrip(" .!?")
    text=re.sub(r"^(?:hey\s+)?(?:spark|jarvis)\s*[,,:]?\s*","",text,flags=re.I)
    match=re.fullmatch(r"(?i)(?:upgrade|improve|enhance)\s+(?:my\s+)?skill\s+("+NAME+r")\s+(?:to|so\s+it\s+can)\s+(.{10,450})",text)
    if match:
        return {"intent":"upgrade","name":match[1].lower(),"goal":match[2].strip()}
    match=re.fullmatch(r"(?i)(?:create|learn|make|build)\s+(?:a\s+)?(?:new\s+)?skill\s+(?:to|that\s+can|for)\s+(.{10,450})",text)
    if match:
        return {"intent":"create","goal":match[1].strip()}
    match=re.fullmatch(r"(?i)(?:activate|enable)\s+(?:the\s+)?tested\s+skill\s+("+NAME+r")",text)
    if match:return {"intent":"activate","name":match[1].lower()}
    if re.fullmatch(r"(?i)(?:list|show)\s+(?:my\s+)?skills",text):
        return {"intent":"list"}
    return None

async def execute_skill_voice(evolution, project, parsed):
    """All source generation and testing remain inside existing Evolution gates."""
    if not isinstance(parsed,dict) or parsed.get("intent") not in {"upgrade","create","activate","list"}:
        return {"ok":False,"message":"Say create skill to, upgrade skill NAME to, or activate tested skill NAME."}
    intent=parsed["intent"]
    try:
        rows=await evolution.execute("list_code_skills",project,{})
        if not isinstance(rows,list):raise ValueError("Skill inventory unavailable.")
        if intent=="list":
            names=sorted({r["name"] for r in rows if isinstance(r,dict) and isinstance(r.get("name"),str)})
            return {"ok":True,"message":"Skills: "+(", ".join(names[:15]) or "none yet")+".","names":names[:15]}
        name=parsed.get("name")
        matches=[r for r in rows if isinstance(r,dict) and r.get("name")==name]
        if intent=="activate":
            tested=[r for r in matches if r.get("status")=="tested"]
            if len(tested)!=1:
                return {"ok":False,"message":"Exactly one tested candidate must exist for that skill. Open Skill Forge to choose a revision."}
            record=await evolution.execute("activate_code_skill",project,{"id":tested[0]["id"],"approved":True})
            if record.get("status")!="active":raise ValueError("Activation not confirmed.")
            return {"ok":True,"message":f"Skill {name} activated after the existing test gate.","id":record["id"]}
        if intent=="upgrade" and not matches:
            return {"ok":False,"message":f"Skill {name} was not found. Say list skills, or ask to create a new skill."}
        goal=parsed["goal"]
        # This request has a bounded natural-language goal, not untrusted code.
        # No previous source text or secrets are transmitted to an inference provider.
        description=(f"Upgrade the existing skill named {name}: {goal}. "
                     f"Return an original compatible pure data transformation with tests."
                     if intent=="upgrade" else goal)
        candidate=await evolution.execute("generate_code_skill",project,{
            "description":description[:1000],"analysis_id":None,"rea_evidence_id":None})
        if not isinstance(candidate,dict) or not isinstance(candidate.get("id"),str):
            raise ValueError("Skill generation returned no candidate.")
        tested=await evolution.execute("test_code_skill",project,{"id":candidate["id"]})
        if not isinstance(tested,dict):
            raise ValueError("Skill testing returned no result.")
        passed=tested.get("status")=="tested"
        if intent=="upgrade" and tested.get("name")!=name:
            return {"ok":False,"message":f"Candidate did not preserve skill name {name}; manual review required.","id":candidate["id"]}
        if not passed:
            return {"ok":False,"message":"Candidate created but tests did not pass. Original skill remains unchanged.","id":candidate["id"]}
        actual=tested.get("name","candidate")
        return {"ok":True,"message":f"Skill {actual} learned as a tested candidate, not active. Say activate tested skill {actual} to promote it.","id":candidate["id"],"status":"tested"}
    except Exception:
        return {"ok":False,"message":"Skill upgrade or activation could not be verified; existing active skill was not intentionally changed."}
