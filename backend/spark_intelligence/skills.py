"""Reviewed SKILL.md instruction data. Importing never grants executable tools."""
import re
from .policy import Improvements


class InstructionalSkills(Improvements):
    def stage(self,project,content,source):
        if not isinstance(content,str) or not 1<=len(content)<=20000 or not isinstance(source,str) or not 1<=len(source)<=300:
            raise ValueError('A bounded SKILL.md and provenance are required')
        normalized=content.replace('\r\n','\n')
        parts=normalized.split('\n---\n',1)
        if not normalized.startswith('---\n') or len(parts)!=2:
            raise ValueError('SKILL.md requires frontmatter and instructions')
        metadata={}
        for line in parts[0][4:].splitlines():
            if not line.strip():
                continue
            if ':' not in line:
                raise ValueError('Only scalar frontmatter fields are supported')
            key,value=line.split(':',1)
            if key in metadata or key not in ('name','description','license','compatibility','depends'):
                raise ValueError('Duplicate, unsupported or permission-granting metadata')
            metadata[key]=value.strip().strip('"\'')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',metadata.get('name','')) or len(metadata['name'])>64 or not 1<=len(metadata.get('description',''))<=1024:
            raise ValueError('Invalid skill name or description')
        if not 1<=len(parts[1].strip())<=10000:
            raise ValueError('Instructions must contain 1–10000 characters')
        candidate=self.propose(project,parts[1],'prompt')
        candidate.update(kind='instructional_skill',name=metadata['name'],metadata=metadata,source=source,permissions=[],validation='not_tested')
        return self.store._save('improvement',project,candidate['id'],candidate)

    def test(self,project,identifier):
        candidate=self.store._get('improvement',project,identifier)
        if candidate['kind']!='instructional_skill' or candidate['status'] not in ('staged','tested'):
            raise ValueError('Select a staged instructional skill')
        dependencies=candidate['metadata'].get('depends','').split(',')
        active={item.get('name') for item in self.list(project) if item['status']=='active'}
        if any(dependency.strip() and dependency.strip() not in active for dependency in dependencies):
            raise ValueError('Skill dependencies are not active')
        candidate.update(status='tested',validation='metadata_and_dependencies_only')
        return self.store._save('improvement',project,identifier,candidate)

    def activate(self,project,identifier,*,approved=False):
        candidate=self.store._get('improvement',project,identifier)
        if approved is not True or candidate['status']!='tested' or candidate['kind']!='instructional_skill':
            raise ValueError('A validated skill and explicit inspection approval are required')
        previous=[item for item in self.list(project) if item.get('name')==candidate['name'] and item['status']=='active']
        candidate['supersedes']=previous[0]['id'] if previous else None
        for item in previous:
            item['status']='superseded'
            self.store._save('improvement',project,item['id'],item)
        candidate['status']='active'
        return self.store._save('improvement',project,identifier,candidate)

    def list(self,project):
        return [item for item in self.store._list('improvement',project) if item['kind']=='instructional_skill']

    def context(self,project,name):
        candidate=next((item for item in self.list(project) if item['name']==name and item['status']=='active'),None)
        if candidate is None:
            raise ValueError('No active instructional skill in this project')
        return {'id':candidate['id'],'instructions':candidate['content'],'permissions':[],'source':candidate['source']}
