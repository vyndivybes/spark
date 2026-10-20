const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {getExperiencePlan} = require('../electron/experience-manager.cjs');

function fixture(){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'spark-exp-'));
  const data=path.join(root,'user-data');
  fs.mkdirSync(path.join(root,'vendor','holo-gestures','sample-notes'),{recursive:true});
  fs.mkdirSync(path.join(root,'vendor','brain-map'),{recursive:true});
  fs.mkdirSync(path.join(root,'scripts'),{recursive:true});
  fs.writeFileSync(path.join(root,'scripts','holo_notes_launcher.py'),'# HOLO launcher');
  fs.writeFileSync(path.join(root,'vendor','holo-gestures','server.py'),'# test');
  fs.writeFileSync(path.join(root,'vendor','holo-gestures','sample-notes','note.md'),'# Test');
  fs.writeFileSync(path.join(root,'vendor','brain-map','build.py'),'# test');
  return {root,data,cleanup:()=>fs.rmSync(root,{recursive:true,force:true})};
}

test('SPARK HOLO launches the original self-hosted Python server with no shell',()=>{
  const x=fixture();try{
    const p=getExperiencePlan('holo',{root:x.root,userData:x.data,python:'python'});
    assert.equal(p.url,'http://127.0.0.1:4890');
    assert.equal(p.steps.length,1);
    assert.equal(p.steps[0].shell,false);
    assert.deepEqual(p.steps[0].args,[path.join(x.root,'scripts','holo_notes_launcher.py')]);
    assert.equal(p.steps[0].env.SPARK_HOLO_NOTES_DIR,
      path.join(x.root,'vendor','holo-gestures','sample-notes'));
    assert.equal(p.steps[0].cwd,path.join(x.root,'vendor','holo-gestures'));
  }finally{x.cleanup()}
});

test('SPARK Neural Atlas renders the Graphify business graph instead of sample notes',()=>{
  const x=fixture();try{
    fs.mkdirSync(path.join(x.root,'vendor','vayu-workspace'),{recursive:true});
    fs.writeFileSync(path.join(x.root,'vendor','vayu-workspace','VAYU-Knowledge-Sphere-Live.html'),
      '<script id="initial-data" type="application/json">{"nodes":[{"id":"prj-vaos","title":"VAOS","type":"project"}],'
      +'"edges":[{"source":"prj-vaos","target":"prj-vyndios"}],"sources":[]}</script>');
    fs.writeFileSync(path.join(x.root,'scripts','neural_atlas_vault.py'),'# generator');
    const p=getExperiencePlan('brain',{root:x.root,userData:x.data,python:'python'});
    assert.equal(p.url,'http://127.0.0.1:4710');
    assert.equal(p.steps.length,3);
    assert.equal(p.steps[0].args[0],path.join(x.root,'scripts','neural_atlas_vault.py'));
    assert.equal(p.steps[0].args[1],'--root');
    assert.equal(p.steps[0].args[3],'--out');
    assert.equal(p.steps[0].args[4],path.join(x.data,'neural-atlas-vault'));
    assert.equal(p.steps[1].args[0],path.join(x.root,'vendor','brain-map','build.py'));
    assert.equal(p.steps[1].args[1],'--vault');
    assert.equal(p.steps[1].args[2],path.join(x.data,'neural-atlas-vault'));
    assert.deepEqual(p.steps[2].args.slice(0,4),['-m','http.server','4710','--bind']);
    assert.ok(p.steps.every(step=>step.shell===false));
  }finally{x.cleanup()}
});

test('Neural Atlas is rejected when the Graphify generator is missing',()=>{
  const x=fixture();try{
    assert.throws(()=>getExperiencePlan('brain',{root:x.root,userData:x.data}),/Neural Atlas generator/);
  }finally{x.cleanup()}
});

test('unknown experiences and missing source checkouts are rejected',()=>{
  const x=fixture();try{
    assert.throws(()=>getExperiencePlan('shell',{root:x.root,userData:x.data}),/Unknown SPARK experience/);
    fs.unlinkSync(path.join(x.root,'vendor','holo-gestures','server.py'));
    assert.throws(()=>getExperiencePlan('holo',{root:x.root,userData:x.data}),/setup:experiences/);
    fs.unlinkSync(path.join(x.root,'vendor','brain-map','build.py'));
    assert.throws(()=>getExperiencePlan('brain',{root:x.root,userData:x.data}),/setup:experiences/);
  }finally{x.cleanup()}
});

test('SPARK identity and launch controls are present in the desktop shell',()=>{
  const app=fs.readFileSync(path.join(__dirname,'../src/App.jsx'),'utf8');
  const pkg=JSON.parse(fs.readFileSync(path.join(__dirname,'../package.json'),'utf8'));
  assert.equal(pkg.name,'spark');
  assert.match(app,/SPARK/);
  assert.match(app,/spark:open-experience/);
});

test('VAYU uses a bounded local launch and user-data storage',()=>{
  const root=path.resolve(__dirname,'..');
  const userData=path.join(os.tmpdir(),'spark-vayu-test-data');
  const plan=getExperiencePlan('vayu',{root,userData,python:'configured-python'});
  assert.equal(plan.url,'http://127.0.0.1:4891');
  assert.equal(plan.page,'/VAYU-Knowledge-Sphere-Live.html');
  assert.equal(plan.steps[0].command,'configured-python');
  assert.equal(plan.steps[0].shell,false);
  assert.equal(plan.steps[0].env.SPARK_VAYU_EXPORTS_DIR,path.join(userData,'vayu-exports'));
  const connected=getExperiencePlan('vayu',{root,userData,vayuExportsDir:path.join(userData,'published-projects')});
  assert.equal(connected.steps[0].env.SPARK_VAYU_EXPORTS_DIR,path.join(userData,'published-projects'));
  assert.deepEqual(plan.steps[0].args,[path.join(root,'scripts','vayu_launcher.py'),'--port','4891','--data-dir',path.join(userData,'vayu-workspace')]);
});

test('VAYU manager starts the real server, reuses its window and stops on close',
  {skip:process.env.SPARK_TEST_VAYU_LAUNCH!=='1'},async()=>{
  const {EventEmitter}=require('node:events');
  const {createExperienceManager}=require('../electron/experience-manager.cjs');
  const userData=fs.mkdtempSync(path.join(os.tmpdir(),'spark-vayu-launch-'));
  let window;
  class LocalWindow extends EventEmitter{
    constructor(options){super();this.options=options;this.dead=false;this.webContents=new EventEmitter();this.webContents.setWindowOpenHandler=()=>{};window=this;}
    isDestroyed(){return this.dead;}
    focus(){this.focused=true;}
    async loadURL(url){this.url=url;const response=await fetch(url);assert.equal(response.status,200);}
    close(){this.dead=true;this.emit('closed');}
  }
  const manager=createExperienceManager({root:path.resolve(__dirname,'..'),userData,
    python:process.env.SPARK_PYTHON||'python',BrowserWindow:LocalWindow});
  try{
    assert.equal((await manager.open('vayu')).reused,false);
    assert.equal(window.options.webPreferences.nodeIntegration,false);
    assert.equal(window.options.webPreferences.sandbox,true);
    assert.match(window.url,/VAYU-Knowledge-Sphere-Live\.html$/);
    assert.equal((await manager.open('vayu')).reused,true);
    assert.equal(window.focused,true);
    window.close();
    await assert.rejects(fetch('http://127.0.0.1:4891/api/workspace?space=business'));
  }finally{manager.stopAll();fs.rmSync(userData,{recursive:true,force:true});}
});

test('HOLO gestures use the selected SPARK vault after publish; Atlas uses Graphify data',()=>{
  const x=fixture();try{
    const vault=path.join(x.data,'workspace','holo-notes');
    fs.mkdirSync(path.join(vault,'carbon'),{recursive:true});
    fs.writeFileSync(path.join(vault,'carbon','layup.md'),'# Layup');
    fs.writeFileSync(path.join(x.root,'scripts','neural_atlas_vault.py'),'# generator');
    const holo=getExperiencePlan('holo',{root:x.root,userData:x.data,notesDir:vault,python:'python'});
    const brain=getExperiencePlan('brain',{root:x.root,userData:x.data,notesDir:vault,python:'python'});
    assert.equal(holo.steps[0].env.SPARK_HOLO_NOTES_DIR,vault);
    assert.equal(brain.steps[1].args[2],path.join(x.data,'neural-atlas-vault'));
    assert.notEqual(brain.steps[1].args[2],vault);
  }finally{x.cleanup()}
});
