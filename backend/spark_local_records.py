"""Read saved local SPARK metadata only. No sample inventory, writes or network calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone

SPACES = {'vayu':'VAYU', 'vyndios':'VYNDI OS', 'vaos':'VAOS', 'personal':'Personal', 'unassigned':'Unassigned'}

def default_root():
    configured = os.environ.get('SPARK_WORKSPACE_DATA_ROOT')
    if configured:
        return Path(configured)
    return Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.spark')/'SPARK'/'workspace'

def _rows(root, path, query, params=()):
    if not path.is_relative_to(root) or any(p.is_symlink() for p in [path, *path.parents] if p.is_relative_to(root)) or not path.is_file() or path.stat().st_size > 64_000_000:
        return []
    try:
        with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=2) as db:
            db.execute('PRAGMA query_only=ON')
            return db.execute(query, params).fetchall()
    except sqlite3.Error:
        return []

def collect_records(data_root=None, vayu_data_root=None):
    root = Path(data_root or default_root()).absolute()
    if root.is_symlink():
        raise ValueError('Linked workspace roots are not supported.')
    records = {}
    warnings = []
    def add(source, identity, title, *, project='', kind='record', date='', status='', space=None):
        if not isinstance(title,str) or not title.strip() or len(records)>=2000:
            return
        title=title.strip()[:300]
        if not space:
            # Only explicit project/title associations; provider identity is not a personal label.
            name=re.sub(r'[^a-z0-9]+',' ',str(project)+' '+title.lower()).lower()
            if re.search(r'\bvyndi(?:os| os)?\b',name):space='vyndios'
            elif re.search(r'\bvaos\b',name):space='vaos'
            elif re.search(r'\bvayu\b',name):space='vayu'
            elif re.search(r'\bpersonal\b',str(project).lower()):space='personal'
            else:space='unassigned'
        identity=hashlib.sha256((source+'|'+str(project)+'|'+str(identity)).encode()).hexdigest()[:24]
        records[identity]={'id':identity,'title':title,'source':source,'project':str(project)[:100], 'space':space,'kind':kind,'date':str(date or '')[:80],'status':str(status or '')[:80]}
    for path in sorted((root/'knowledge').glob('*/knowledge.sqlite3')):
        for identity,title,date in _rows(root,path,'SELECT id,name,uploaded FROM documents ORDER BY uploaded DESC LIMIT 200'):
            add('Local documents',identity,title,project=path.parent.name,kind='document',date=date)
    for path in sorted((root/'workbench').glob('*/workspace.sqlite3')):
        for identity,kind,body in _rows(root,path,"SELECT id,kind,body FROM items WHERE kind IN ('agenda','routine') LIMIT 200"):
            try:
                item=json.loads(body)
                add('Local '+kind,identity,item.get('title') or item.get('name'),project=path.parent.name,kind='task' if kind=='agenda' else 'routine',date=item.get('due'),status='done' if item.get('done') else 'open')
            except (ValueError,TypeError,AttributeError):warnings.append('A local agenda record could not be read.')
    for service,tool,body,state,observed in _rows(root,root/'integration-sync/snapshots.sqlite3','SELECT service,tool,body,state,last_success FROM snapshots ORDER BY last_success LIMIT 200'):
        if state != 'current':
            continue
        try:
            saved=json.loads(body)
            if saved.get('ok') is not True:continue
            data=saved.get('data',{})
            if service=='google-drive':
                for item in data.get('files',[])[:200]:add('Saved Drive metadata',item.get('id'),item.get('name'),kind='document',date=item.get('modified'))
            elif service=='gmail':
                for item in data.get('messages',[])[:200]:add('Saved Gmail metadata',item.get('id'),item.get('subject'),kind='message',date=item.get('date'))
            elif service=='google-calendar':
                for item in data.get('tasks',[])[:200]:add('Saved Google tasks',item.get('id'),item.get('title'),kind='task',date=item.get('due'),status=item.get('status'))
                for item in data.get('events',[])[:200]:add('Saved Calendar metadata',item.get('id'),item.get('summary'),kind='event',date=item.get('start',{}).get('dateTime') or item.get('start',{}).get('date'))
            elif service=='github':
                repository=saved.get('repository','')
                if isinstance(data,list):
                    for item in data[:200]:add('Saved GitHub metadata',str(repository)+'/'+str(item.get('number')),item.get('title'),project=repository,kind='task',status=item.get('state'))
                elif isinstance(data,dict):add('Saved GitHub metadata',repository,data.get('nameWithOwner'),project=repository,kind='repository')
            elif service=='obsidian':
                for item in saved.get('notes',[])[:200]:
                    parts=str(item.get('path','')).replace('\\','/').split('/')
                    # Exclude bundled/default vault notes; only explicit SPARK publications qualify.
                    if len(parts)>=3 and parts[0]=='Spark-Connected':add('Published local notes',item.get('path'),item.get('name'),project=parts[1],kind='document')
        except (ValueError,TypeError,AttributeError):warnings.append('A saved integration snapshot could not be read.')
    for kind,project,identity,body in _rows(root,root/'intelligence/intelligence.sqlite3',"SELECT kind,project,id,body FROM records WHERE kind='job' LIMIT 200"):
        try:
            item=json.loads(body)
            add('Local agent tasks',identity,item.get('title'),project=project,kind='task',date=item.get('created_at'),status=item.get('state'))
        except (ValueError,TypeError,AttributeError):warnings.append('A local task could not be read.')
    if vayu_data_root:
        legacy=Path(vayu_data_root).absolute()
        for name in ('business','personal'):
            path=legacy/'workspace-data'/(name+'.json')
            if any(p.is_symlink() for p in (legacy,path.parent,path)) or not path.is_file() or path.stat().st_size>2_000_000:continue
            try:
                saved=json.loads(path.read_text(encoding='utf-8'))
                for item in saved.get('items',[])[:1000]:
                    add('Saved '+name+' register',item.get('id'),item.get('title'),project=name,kind=item.get('kind','record'),date=item.get('dueDate'),status=item.get('status'),space='personal' if name=='personal' else 'vayu')
            except (OSError,ValueError,AttributeError):warnings.append('A saved register could not be read.')
    values=sorted(records.values(),key=lambda x:(x['space'],x['source'],x['title'].lower()))
    return {'records':values,'spaces':[{'id':key,'label':label,'count':sum(r['space']==key for r in values)} for key,label in SPACES.items()], 'source':'Existing local SPARK records','readAt':datetime.now(timezone.utc).isoformat(),'warnings':sorted(set(warnings)), 'scope':'Saved local metadata only. No external refresh, document bodies, sample data, or inferred business relationships.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--vayu-data-root',type=Path)
    args=parser.parse_args();print(json.dumps(collect_records(args.data_root,args.vayu_data_root),ensure_ascii=True))
