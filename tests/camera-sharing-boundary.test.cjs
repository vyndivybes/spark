const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const read = name => fs.readFileSync(path.join(__dirname, '..', name), 'utf8');
const app = read('src/App.jsx');
const server = read('backend/server.py');

test('webcam preview stays local until Gemini streaming receives explicit approval', () => {
    assert.match(app, /cameraShareRef = useRef\(false\)/);
    assert.match(app, /socket\.emit\('set_camera_sharing', \{enabled: requested\}\)/);
    assert.match(app, /socket\.on\('camera_sharing_status'/);
    assert.match(app, /onClick=\{toggleCameraSharing\}/);
    assert.ok(app.includes('cameraShareRef.current &&'));
    assert.ok(app.includes('groqVisionAvailableRef.current'));
    assert.match(app, /isVideoOnRef\.current && cameraShareRef\.current && socket\.connected/);
});

test('server enforces owner, selected Gemini provider and explicit consent', () => {
    assert.match(server, /async def set_camera_sharing\(sid, data\)/);
    assert.match(server, /if not can_stream_camera\(/);
    assert.match(server, /if now - camera_frame_last_at < 0\.9:/);
    assert.match(server, /await audio_loop\.send_frame\(frame\)/);
});

test('disconnect and camera stop revoke sharing without touching voice', () => {
    assert.match(app, /const stopVideo = \(\) => \{/);
    assert.match(app, /socket\.emit\('set_camera_sharing', \{enabled: false\}\)/);
    assert.match(server, /camera_share_sid = None/);
});
