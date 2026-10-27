const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {getExperiencePlan}=require('../electron/experience-manager.cjs');

// Active launch targets use the knowledge dashboards and real local records.
function fixture(){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'spark-experiences-'));
  const data=path.join(root,'user-data');
  fs.mkdirSync(path.join(root,'scripts'),{recursive:true});
  for(const file of ['spark_knowledge_dashboard.py','spark_obsidian_dashboard.py'])
    fs.writeFileSync(path.join(root,'scripts',file),'# local dashboard');
  return {root,data,cleanup:()=>fs.rmSync(root,{recursive:true,force:true})};
}

for(const [name,port] of [['graphify',4720],['graphiti',4721],['hermes',4722]]) {
  test(name+' uses configured Python, a fixed loopback port and an explicit mode',()=>{
    const x=fixture();try{
      const plan=getExperiencePlan(name,{root:x.root,userData:x.data,python:'configured-python'});
      assert.equal(plan.url,'http://127.0.0.1:'+port);
      assert.equal(plan.steps.length,1);
      const step=plan.steps[0];
      assert.equal(step.command,'configured-python');
      assert.equal(step.shell,false);
      assert.equal(step.once,false);
      assert.equal(step.cwd,x.root);
      assert.deepEqual(step.args,[path.join(x.root,'scripts','spark_knowledge_dashboard.py'),'--mode',name,'--port',String(port),'--root',x.root]);
    } finally {x.cleanup();}
  });
}

test('Obsidian uses the selected vault without a shell and respects host configuration',()=>{
  const x=fixture();const previous=process.env.SPARK_OBSIDIAN_VAULT;
  try{
    delete process.env.SPARK_OBSIDIAN_VAULT;
    const vault=path.join(x.data,'chosen-vault');
    const plan=getExperiencePlan('obsidian',{root:x.root,userData:x.data,notesDir:vault,python:'configured-python'});
    assert.equal(plan.url,'http://127.0.0.1:4723');
    assert.equal(plan.steps[0].shell,false);
    assert.equal(plan.steps[0].env.SPARK_OBSIDIAN_VAULT,vault);
    assert.deepEqual(plan.steps[0].args,[path.join(x.root,'scripts','spark_obsidian_dashboard.py'),'--port','4723','--vault',vault,'--root',x.root]);
    process.env.SPARK_OBSIDIAN_VAULT=path.join(x.data,'host-selected-vault');
    assert.equal(getExperiencePlan('obsidian',{root:x.root,userData:x.data,notesDir:vault}).steps[0].env.SPARK_OBSIDIAN_VAULT,process.env.SPARK_OBSIDIAN_VAULT);
  } finally {if(previous===undefined)delete process.env.SPARK_OBSIDIAN_VAULT;else process.env.SPARK_OBSIDIAN_VAULT=previous;x.cleanup();}
});

test('unknown and retired targets are refused without executing arbitrary commands',()=>{
  const x=fixture();try{
    for(const name of ['shell','holo','brain','vayu','https://example.com','graphify; whoami'])
      assert.throws(()=>getExperiencePlan(name,{root:x.root,userData:x.data}),/Unknown SPARK experience/);
    assert.throws(()=>getExperiencePlan('graphify',{}),/paths are unavailable/);
  } finally {x.cleanup();}
});

test('missing knowledge and Obsidian wrappers produce actionable failures',()=>{
  const x=fixture();try{
    fs.unlinkSync(path.join(x.root,'scripts','spark_knowledge_dashboard.py'));
    assert.throws(()=>getExperiencePlan('graphify',{root:x.root,userData:x.data}),/knowledge dashboard is missing/);
    fs.unlinkSync(path.join(x.root,'scripts','spark_obsidian_dashboard.py'));
    assert.throws(()=>getExperiencePlan('obsidian',{root:x.root,userData:x.data}),/Obsidian dashboard is missing/);
  } finally {x.cleanup();}
});

test('SPARK identity and launch controls remain reachable',()=>{
  const app=fs.readFileSync(path.join(__dirname,'../src/App.jsx'),'utf8');
  assert.equal(JSON.parse(fs.readFileSync(path.join(__dirname,'../package.json'),'utf8')).name,'spark');
  assert.match(app,/spark:open-experience/);
});
