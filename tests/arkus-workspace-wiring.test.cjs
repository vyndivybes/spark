const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const read = p => fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');
const app=read('src/App.jsx'), panel=read('src/components/WorkspacePanel.jsx');
const server=read('backend/server.py'), api=read('backend/spark_workspace.py');

test('actual ARKUS workspace is mounted in the SPARK cockpit, not a mockup',()=>{
  const command=read('src/components/CommandCenter.jsx');
  assert.match(app,/import CommandCenter from '.\/components\/CommandCenter'/);
  assert.match(app,/DASHBOARD/);
  assert.match(app,/showWorkspace && <CommandCenter socket=\{socket\}/);
  assert.match(command,/import WorkspacePanel from '.\/WorkspacePanel'/);
  assert.match(command,/<WorkspacePanel key=\{page\} socket=\{socket\} visible project=\{project\}/);
  for(const action of ['import_document','search_documents','list_documents','remove_document',
                        'propose_skill','test_skill','activate_skill','run_skill','revise_skill','rollback_skill']){
    assert.ok(api.includes('"'+action+'"'),action+' action must be implemented');
    assert.ok(panel.includes("'"+action+"'") || panel.includes('"'+action+'"'), action+' action must be accessible from UI');
  }
});

test('workspace operations are owner-bound and never grant remote tools',()=>{
  assert.match(server,/async def workspace_action\(sid, data\):/);
  assert.match(server,/getattr\(audio_loop, "owner_sid", None\) == sid/);
  assert.match(server,/getattr\(audio_loop, "session", None\) is not None/);
  assert.match(server,/await asyncio\.to_thread\(spark_workspace\.execute,action,project,payload\)/);
  assert.match(server,/await sio\.emit\("workspace_result"/);
  assert.doesNotMatch(api,/subprocess|shell=True|exec\(/);
});

test('offline file bytes and declarative JSON skills are explicitly bounded',()=>{
  assert.match(panel,/file\.size>2_000_000/);
  assert.match(panel,/file\.arrayBuffer\(\)/);
  assert.match(panel,/JSON\.parse\(skillDraft\)/);
  assert.match(api,/from arkus_knowledge_base import KnowledgeBase/);
  assert.match(api,/from arkus_skill_forge import SkillForge/);
});
