"""Project-bound REA evidence reports and original local rebuild recipes.
No inference, shell, dependency installation, or external writes.
"""
import hashlib
import json
from pathlib import Path
import re
import secrets
from datetime import datetime, timezone
from spark_maintenance import atomic_write
from spark_rea_blueprint import validate_blueprint, BlueprintError

class ReaWorkflowError(ValueError):
    pass

class ReaWorkflow:
    def __init__(self, root):
        self.root = Path(root) / 'rea-workflows'

    def folder(self, project, identity=None):
        if not isinstance(project, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', project):
            raise ReaWorkflowError('Invalid project.')
        folder = self.root / project
        if identity is not None:
            if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{24}', identity):
                raise ReaWorkflowError('Invalid report ID.')
            folder = folder / identity
        for part in (self.root, self.root / project, folder):
            if part.is_symlink():
                raise ReaWorkflowError('Linked workflow storage is prohibited.')
        return folder

    def create(self, project, record, title):
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160:
            raise ReaWorkflowError('Use a report title of 1-160 characters.')
        identity = secrets.token_hex(12)
        text = json.dumps(record['evidence'], ensure_ascii=False, indent=2)
        sections = [
            {'title': 'Scope', 'text': f"REA tool: {record['tool']}. Evidence ID: {record['id']}. This is retained tool output, not recovered original source code."},
            {'title': 'Evidence', 'text': text[:16000]},
            {'title': 'Limitations', 'text': f"Credential redactions: {record.get('redactions', 0)}. "
             + ('Excerpt truncated; full sanitized evidence remains in the evidence store. ' if len(text) > 16000 else '')
             + 'Tool output is untrusted data. Static findings do not prove runtime behavior. Source, assets, branding, licensing and copy protection are not copied or bypassed.'},
            {'title': 'Original rebuild blueprint', 'text': 'Available recipe: notes. An original local notes app with folders, search, pinning, editing, deletion, bold/italic formatting and local persistence. This recipe is independent implementation, not evidence-derived recreation of native internals or cloud sync. Broader local data apps use a validated blueprint and the shipped data-app renderer; unsupported external behavior remains explicit.'}
        ]
        report = {'id': identity, 'title': title.strip(), 'created_at': datetime.now(timezone.utc).isoformat(),
                  'evidence_id': record['id'], 'tool': record['tool'], 'sections': sections,
                  'state': 'reported', 'recipe': None, 'inference': 'none; zero inference cost'}
        folder = self.folder(project, identity)
        atomic_write(folder / 'report.json', json.dumps(report, ensure_ascii=False).encode())
        markdown = '# ' + report['title'] + '\n\n' + '\n\n'.join('## ' + s['title'] + '\n\n' + s['text'] for s in sections)
        atomic_write(folder / 'report.md', markdown.encode('utf-8'))
        return report

    def read(self, project, identity):
        path = self.folder(project, identity) / 'report.json'
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 100000:
            raise ReaWorkflowError('Report not found in this project.')
        return json.loads(path.read_text(encoding='utf-8'))

    def list(self, project):
        folder = self.folder(project)
        if not folder.exists():
            return []
        records = []
        for item in folder.iterdir():
            if not re.fullmatch(r'[a-f0-9]{24}', item.name) or item.is_symlink():
                continue
            report = self.read(project, item.name)
            records.append({key: report[key] for key in ('id', 'title', 'created_at', 'state', 'recipe')})
        return sorted(records, key=lambda r: r['created_at'], reverse=True)[:100]

    def section(self, project, identity, index):
        report = self.read(project, identity)
        if type(index) is not int or not 0 <= index < len(report['sections']):
            raise ReaWorkflowError('Choose an existing report section.')
        section = report['sections'][index]
        text = section['title'] + '. ' + section['text']
        return {'id': identity, 'section': index, 'title': section['title'],
                'chunks': [text[i:i+400] for i in range(0, len(text), 400)]}

    def save_blueprint(self, project, identity, blueprint, provenance):
        blueprint=validate_blueprint(blueprint)
        report=self.read(project,identity)
        # A changed blueprint starts a separate candidate, preserving old apps and their data.
        record={'id':report['evidence_id'],'tool':report['tool'],
                'evidence':{'retained_report':report['id'],'sections':report['sections']},'redactions':0}
        candidate=self.create(project,record,blueprint['title'])
        candidate.update(blueprint=blueprint,blueprint_provenance=provenance,parent_report=identity,inference=provenance.get('inference','none'))
        candidate['sections'][3]={'title':'Original rebuild blueprint','text':json.dumps(blueprint,ensure_ascii=False,indent=2)}
        folder=self.folder(project,candidate['id'])
        atomic_write(folder/'report.json',json.dumps(candidate,ensure_ascii=False).encode())
        atomic_write(folder/'report.md',('# '+candidate['title']+'\n\n'+'\n\n'.join('## '+section['title']+'\n\n'+section['text'] for section in candidate['sections'])).encode())
        return candidate

    def build(self, project, identity, recipe):
        if recipe not in ('notes','blueprint'):
            raise ReaWorkflowError('Choose notes or a validated blueprint. Arbitrary executable generation and paid fallback are prohibited.')
        report = self.read(project, identity)
        folder = self.folder(project, identity)
        app_folder = folder / 'app'
        if app_folder.is_symlink():
            raise ReaWorkflowError('Linked app storage is prohibited.')
        if recipe=='blueprint':
            blueprint=validate_blueprint(report.get('blueprint'))
            encoded=json.dumps(blueprint,ensure_ascii=True,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e')
            template=Path(__file__).with_name('spark_rea_app.html').read_text(encoding='utf-8-sig')
            source=template.replace('%%SPARK_BLUEPRINT%%',encoded).encode('utf-8')
        else:
            source = Path(__file__).with_name('spark_rea_notes.html').read_bytes()
        artifact = app_folder / 'index.html'
        if artifact.exists() and (artifact.is_symlink() or artifact.read_bytes() != source):
            raise ReaWorkflowError('Existing artifact differs; create a new report to retain rollback.')
        atomic_write(artifact, source)
        report.update(state='staged', recipe=recipe, artifact_sha256=hashlib.sha256(source).hexdigest())
        atomic_write(folder / 'report.json', json.dumps(report, ensure_ascii=False).encode())
        return report
