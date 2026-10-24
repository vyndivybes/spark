"""Exact, project-bound REA voice intents; no arbitrary tool or shell access."""
import re

def parse_rea_command(text):
    if not isinstance(text,str):return None
    text=re.sub(r'\blatest rea (report|app)\b',r'rea \1 latest',text,flags=re.I)
    match=re.fullmatch(r'reverse engineer (?:website )?(https://[^\s]{1,350})',text,re.I)
    if match:return {'action':'rea_workflow_analyze','payload':{'kind':'website','target':match[1]}}
    match=re.fullmatch(r'reverse engineer app (.{1,350})',text,re.I)
    if match:return {'action':'rea_workflow_analyze','payload':{'kind':'artifact','target':match[1].strip('"')}}
    if re.fullmatch(r'(?:show|list) (?:my |saved )?rea reports',text,re.I):
        return {'action':'rea_workflow_list','payload':{}}
    match=re.fullmatch(r'read rea report (latest|[a-f0-9]{24}) section ([1-4])(?: part ([1-9][0-9]?))?',text,re.I)
    if match:
        return {'action':'rea_workflow_voice_section','payload':{'id':match[1].lower(),'section':int(match[2])-1,'part':int(match[3] or 1)-1}}
    match=re.fullmatch(r'build notes from rea report (latest|[a-f0-9]{24})',text,re.I)
    if match:return {'action':'rea_workflow_build','payload':{'id':match[1].lower(),'recipe':'notes'}}
    match=re.fullmatch(r'(test|open) rea app (latest|[a-f0-9]{24})',text,re.I)
    if match:return {'action':'rea_workflow_preview','payload':{'id':match[2].lower(),'action':match[1].lower()}}
    return None
