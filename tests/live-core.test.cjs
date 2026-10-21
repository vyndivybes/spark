const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');

test('SPARK uses supported Gemini Live model and true real-time audio send',()=>{
  const spark=read('backend/spark.py');
  assert.match(spark,/MODEL\s*=\s*live_model\(\)/);
  assert.match(spark,/send_realtime_input\(\s*audio=/);
  assert.match(spark,/audio\/pcm;rate=16000/);
  assert.doesNotMatch(spark,/MODEL\s*=\s*["']models\/gemini-2\.5/);
});
test('SPARK never reports model connected before Live handshake',()=>{
  const server=read('backend/server.py');
  assert.doesNotMatch(server,/await sio\.emit\('status',\s*\{'msg':\s*'A\.D\.A Started'\}\)/);
  assert.match(server,/live_state/);
  assert.match(server,/setup_required/);
  assert.match(server,/ai_status/);
});
test('SPARK can explicitly borrow local ARKUS credential without saving it or echoing it',()=>{
  const setup=read('start-spark.ps1');
  assert.match(setup,/UseArkusGeminiKey/);
  assert.match(setup,/ARKUS.*config\.json|arkus\\config\.json/i);
  assert.match(setup,/GEMINI_API_KEY/);
  assert.doesNotMatch(setup,/Write-Host\s+\$.*api_key/);
});
test('SPARK UI shows failure state instead of silently reporting resumed audio',()=>{
  const app=read('src/App.jsx');
  assert.match(app,/socket\.on\('ai_status'/);
  assert.match(app,/setup_required/);
  assert.doesNotMatch(app,/micDevices\.length\s*>\s*0\s*&&\s*!hasAutoConnectedRef/);
});

test('SPARK CORE is an actionable voice activation control, not decorative text',()=>{
  const app=read('src/App.jsx');
  assert.match(app,/const activateSparkCore\s*=\s*\(\)\s*=>/);
  assert.match(app,/onClick=\{activateSparkCore\}/);
  assert.match(app,/ACTIVATE CORE/);
});
