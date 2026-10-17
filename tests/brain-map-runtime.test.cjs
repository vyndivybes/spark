const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const {experiencePythonEnvironment,formatBuildFailure}=require('../electron/experience-manager.cjs');

test('Brain Map Python runs in UTF-8 despite Windows legacy CP1252 redirection',()=>{
  const env=experiencePythonEnvironment({PYTHONIOENCODING:'cp1252',PYTHONUTF8:'0',EXISTING:'keep'});
  assert.equal(env.PYTHONIOENCODING,'utf-8');
  assert.equal(env.PYTHONUTF8,'1');
  assert.equal(env.EXISTING,'keep');
});

test('Brain Map error reporting preserves final exception instead of first 150 chars',()=>{
  const stderr=['Traceback (most recent call last):','  File "C:\\Users\\ASUS\\spark\\vendor\\brain-map\\build.py", line 231',
    '    print("✓ graph built")','UnicodeEncodeError: charmap codec cannot encode character'].join('\n');
  const result=formatBuildFailure(stderr);
  assert.match(result,/UnicodeEncodeError/);
  assert.match(result,/charmap codec/);
  assert.ok(result.length<=650);
});

test('original pinned upstream Brain Map completes with non-ASCII console output',()=>{
  const root=path.join(__dirname,'..');
  const builder=path.join(root,'vendor','brain-map','build.py');
  const vault=path.join(root,'vendor','holo-gestures','sample-notes');
  assert.ok(fs.existsSync(builder),'Run git submodule update --init --recursive');
  assert.ok(fs.existsSync(vault),'HOLO sample Markdown notes missing');
  const rootOut=fs.mkdtempSync(path.join(os.tmpdir(),'spark brain output '));
  try{
    const python=process.env.SPARK_PYTHON||(process.platform==='win32'?'python':'python3');
    const result=spawnSync(python,[builder,'--vault',vault,'--out',path.join(rootOut,'brain')],
      {cwd:path.dirname(builder),env:experiencePythonEnvironment(process.env),
       encoding:'utf8',timeout:20000,windowsHide:true,shell:false});
    assert.equal(result.status,0,result.stderr||result.error?.message);
    assert.match(result.stdout,/notes/);
    assert.ok(fs.existsSync(path.join(rootOut,'brain','graph-data.js')));
    assert.ok(fs.existsSync(path.join(rootOut,'brain','index.html')));
  } finally {fs.rmSync(rootOut,{recursive:true,force:true});}
});
