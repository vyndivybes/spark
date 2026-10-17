const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const app = fs.readFileSync(path.join(__dirname, '../src/App.jsx'), 'utf8');
const ada = fs.readFileSync(path.join(__dirname, '../backend/ada.py'), 'utf8');

test('opt-in video transmission requires connected Gemini Live and active webcam', () => {
  assert.match(app, /if \(isConnected && socketConnected && isVideoOnRef\.current && liveState\.state === 'connected'\)/);
  assert.match(app, /frameNow - lastSentCameraFrameRef\.current >= 1000/);
});

test('webcam sends binary JPEG rather than unchecked blobs', () => {
  assert.match(app, /await blob\.arrayBuffer\(\)/);
  assert.match(app, /socket\.emit\('video_frame', \{ image \}\)/);
});

test('Gemini receives images without waiting for speech activity', () => {
  const start = ada.indexOf('async def send_frame(');
  const end = ada.indexOf('async def send_realtime(', start);
  assert.ok(start !== -1 && end > start);
  const method = ada.slice(start, end);
  assert.match(method, /put_nowait\(self\._latest_image_payload\)/);
  assert.match(method, /except asyncio\.QueueFull/);
});
