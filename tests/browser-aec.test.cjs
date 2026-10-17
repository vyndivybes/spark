const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const read = p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');

test('worklet batches 16k mono PCM without routing mic into speaker',()=>{
  const src=read('public/spark-mic.worklet.js');
  assert.match(src,/class SparkMicProcessor extends AudioWorkletProcessor/);
  assert.match(src,/sampleRate/);
  assert.match(src,/16000/);
  assert.match(src,/Int16Array/);
  assert.match(src,/this\.port\.postMessage/);
  assert.match(src,/fill\(0\)/);
});
test('renderer uses actual Chromium echoCancellation and speaker playback for AEC reference',()=>{
  const src=read('src/audio/BrowserEchoAudio.mjs');
  assert.match(src,/echoCancellation:\s*true/);
  assert.match(src,/getSettings\(\)\?\.echoCancellation/);
  assert.match(src,/createMediaStreamSource/);
  assert.match(src,/createBufferSource/);
  assert.match(src,/audioContext\.destination/);
  assert.match(src,/browser_mic_pcm/);
  assert.match(src,/browser_audio/);
});
test('browser mode bypasses native PyAudio input and speaker paths and manual turn lock',()=>{
  const ada=read('backend/ada.py');
  const backend=read('backend/server.py');
  const app=read('src/App.jsx');
  assert.match(ada,/if not self\.browser_audio:/);
  assert.match(ada,/on_browser_audio/);
  assert.match(backend,/async def browser_mic_pcm/);
  assert.match(backend,/async def browser_audio_ready/);
  assert.match(backend,/owner_sid/);
  assert.match(app,/BrowserEchoAudio/);
  assert.match(app,/browser_aec/);
});
