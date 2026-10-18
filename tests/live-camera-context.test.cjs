const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const app = fs.readFileSync(path.join(__dirname, '../src/App.jsx'), 'utf8');
const ada = fs.readFileSync(path.join(__dirname, '../backend/ada.py'), 'utf8');

test('opt-in video transmission requires connected Gemini Live and active webcam', () => {
  assert.ok(app.includes('if (isConnected && socketConnected && isVideoOnRef.current &&'));
  assert.ok(app.includes('cameraShareRef.current &&'));
  assert.ok(app.includes("liveStateRef.current === 'connected'"));
  assert.match(app, /frameNow - lastSentCameraFrameRef\.current >= 1000/);
});

test('revoked Gemini camera sharing prevents a typed turn from reusing the image', () => {
  const backend = fs.readFileSync(path.join(__dirname, '../backend/server.py'), 'utf8');
  assert.ok(backend.includes('if camera_share_sid == sid and audio_loop._latest_image_payload:'));
  assert.ok(backend.includes('audio_loop._latest_image_payload = None'));
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
