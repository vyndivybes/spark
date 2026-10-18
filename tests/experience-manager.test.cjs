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

test('SPARK Brain Map builds the original wikilink atlas from local notes',()=>{
  const x=fixture();try{
    const p=getExperiencePlan('brain',{root:x.root,userData:x.data,python:'python'});
    assert.equal(p.url,'http://127.0.0.1:4710');
    assert.equal(p.steps.length,2);
    assert.equal(p.steps[0].args[0],path.join(x.root,'vendor','brain-map','build.py'));
    assert.equal(p.steps[0].args[1],'--vault');
    assert.equal(p.steps[0].args[2],path.join(x.root,'vendor','holo-gestures','sample-notes'));
    assert.deepEqual(p.steps[1].args.slice(0,4),['-m','http.server','4710','--bind']);
    assert.ok(p.steps.every(step=>step.shell===false));
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

test('both original HOLO gestures and Brain Map use selected SPARK vault after publish',()=>{
  const x=fixture();try{
    const vault=path.join(x.data,'workspace','holo-notes');
    fs.mkdirSync(path.join(vault,'carbon'),{recursive:true});
    fs.writeFileSync(path.join(vault,'carbon','layup.md'),'# Layup');
    const holo=getExperiencePlan('holo',{root:x.root,userData:x.data,notesDir:vault,python:'python'});
    const brain=getExperiencePlan('brain',{root:x.root,userData:x.data,notesDir:vault,python:'python'});
    assert.equal(holo.steps[0].env.SPARK_HOLO_NOTES_DIR,vault);
    assert.equal(brain.steps[0].args[2],vault);
  }finally{x.cleanup()}
});
