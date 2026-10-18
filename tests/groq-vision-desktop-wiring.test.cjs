const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');
const ui=read('src/App.jsx');
const srv=read('backend/server.py');
const groq=read('backend/spark_groq.py');
test('Groq vision must be opted into and sends frames only to ephemeral local cache',()=>{
  assert.match(ui, /SHARE WITH GROQ VISION/);
  assert.match(ui, /cameraShareRef\.current && aiProviderRef\.current === 'groq'/);
  assert.match(srv, /audio_loop\.set_camera_frame\(frame\)/);
  assert.match(srv, /if not can_groq_vision_frame\(/);
  assert.match(srv, /audio_loop\.clear_camera_frame\(\)/);
});
test('Voice launches are determined and approved by server, never by model-generated shell',()=>{
  assert.match(groq, /parse_desktop_command\(prompt\)/);
  assert.match(srv, /on_desktop_approval=on_desktop_approval/);
  assert.match(srv, /"tool_confirmation_request"/);
  assert.match(srv, /owner_sid.*sid/);
});
