"""User-published project snapshots for VAYU; private documents stay private."""
import json
import os
from pathlib import Path
import secrets
from datetime import datetime, timezone


class VayuExports:
    def __init__(self, workspace, productivity, runtime):
        self.workspace,self.productivity,self.runtime=workspace,productivity,runtime
        self.root=workspace.skills.root.parent/'vayu-exports'

    def path(self, project):
        self.workspace.skills._file(project)
        path=self.root/(project+'.json')
        if self.root.is_symlink() or path.is_symlink():
            raise ValueError('Linked VAYU exports are not allowed.')
        return path

    def revoke(self, project):
        with self.workspace.knowledge.lock:
            self.path(project).unlink(missing_ok=True)
        return {'project':project,'published':False}

    def publish(self, project, jobs=None):
        with self.workspace.knowledge.lock:
            return self._publish(project,jobs)

    def _publish(self, project, jobs=None):
        path=self.path(project)
        documents=[]
        for item in self.workspace._published(project)[:200]:
            note=self.workspace._holo_path(project,item['id'])
            documents.append({'id':item['id'],'title':item['name'],'body':note.read_text(encoding='utf-8')[:5000]})
        agenda=self.productivity.snapshot(project)['agenda']
        jobs=(self.runtime.jobs(project) if jobs is None else jobs)[:200]
        tasks=[{'id':'agenda-'+item['id'],'title':item['title'],'status':'done' if item['done'] else 'open',
                'due':item['due'],'kind':item['kind']} for item in agenda]
        tasks += [{'id':'job-'+item['id'],'title':item.get('title','Agent task'),
                   'status':item.get('state','unknown'),'due':'','kind':'agent'} for item in jobs]
        now=datetime.now(timezone.utc).isoformat()
        nodes=[{'id':'project','title':project,'type':'project','summary':'Published Spark project snapshot.'}]
        nodes += [{'id':'note-'+item['id'],'title':item['title'],'type':'document','summary':item['body']} for item in documents]
        nodes += [{'id':item['id'],'title':item['title'],'type':'record','summary':item['status'],'status':item['status']} for item in tasks]
        edges=[{'source':'project','target':node['id'],'type':'contains'} for node in nodes[1:]]
        value={'format':'spark-vayu-project-v1','project':project,'publishedAt':now,'scope':'Explicitly published notes and current task states; snapshot, not a live feed.',
               'documents':documents,'tasks':tasks,'nodes':nodes,'edges':edges}
        raw=json.dumps(value,ensure_ascii=True)
        if len(raw.encode())>2_000_000:
            raise ValueError('Project snapshot exceeds 2 MB. Publish fewer notes.')
        self.root.mkdir(parents=True,exist_ok=True)
        pending=path.with_suffix('.'+secrets.token_hex(5)+'.tmp')
        try:
            pending.write_text(raw,encoding='utf-8')
            os.replace(pending,path)
        finally:pending.unlink(missing_ok=True)
        return {'project':project,'published':True,'documents':len(documents),'tasks':len(tasks),'publishedAt':now}
