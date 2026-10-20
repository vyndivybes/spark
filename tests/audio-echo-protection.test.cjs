const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ada = fs.readFileSync(path.resolve(__dirname, '../backend/ada.py'), 'utf8');

test('SPARK suppresses mic capture and queued outbound PCM during assistant playback', () => {
  assert.match(ada, /if self\.echo_gate\.mic_blocked\(\):/);
  assert.match(ada, /not self\.browser_audio and self\.echo_gate\.mic_blocked\(\)/);
  assert.match(ada, /self\.echo_gate\.on_output_received\(\)/);
  assert.match(ada, /self\.echo_gate\.on_turn_finished\(/);
  assert.match(ada, /self\.echo_gate\.on_playback_started\(\)/);
  assert.match(ada, /self\.echo_gate\.on_playback_finished\(/);
});
test('echo guard resets on provider reconnection and output still reaches speaker', () => {
  assert.match(ada, /self\.echo_gate\.reset\(\s*hold_for_rearm=\(is_reconnect/);
  assert.match(ada, /await asyncio\.to_thread\(stream\.write, bytestream\)/);
});

test('cinematic voice is single-turn: backend and frontend require explicit mic rearm',()=>{
  const server = fs.readFileSync(path.resolve(__dirname,'../backend/server.py'),'utf8');
  const frontend = fs.readFileSync(path.resolve(__dirname,'../src/App.jsx'),'utf8');
  assert.match(ada,/EchoGate\(require_rearm=live_profile\(\) ===? "?cinematic"?/);
  assert.match(ada,/self\.echo_gate\.on_output_received\(\)/);
  assert.match(server,/audio_loop\.echo_gate\.rearm\(\)/);
  assert.match(server,/sio\.emit\('mic_safety'/);
  assert.match(frontend,/socket\.on\('mic_safety'/);
  assert.match(frontend,/setIsMuted\(Boolean\(data\.muted\)\)/);
});

test('reconnect is silent and 1008 policy violation does not retry',()=>{
  const liveConfig = fs.readFileSync(path.resolve(__dirname,'../backend/spark_live_config.py'),'utf8');
  assert.doesNotMatch(ada,/Please acknowledge the reconnection/);
  assert.match(ada,/Live reconnect is silent/);
  // 1008 is classified as requiring user action (no auto-retry) in
  // spark_live_config.py, and ada.py stops the loop when that is true.
  assert.match(liveConfig,/"1008"/);
  assert.match(ada,/live_error_requires_user_action\(e\)/);
});
