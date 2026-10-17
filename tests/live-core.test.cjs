const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');

test('SPARK uses supported Gemini Live model and true real-time audio send',()=>{
  const ada=read('backend/ada.py');
  assert.match(ada,/MODEL\s*=\s*live_model\(\)/);
  assert.match(ada,/send_realtime_input\(audio=/);
  assert.match(ada,/audio\/pcm;rate=16000/);
  assert.doesNotMatch(ada,/MODEL\s*=\s*["']models\/gemini-2\.5/);
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
