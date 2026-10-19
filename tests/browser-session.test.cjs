const { test } = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');

class Socket extends EventEmitter {
    connected = true;
    sent = [];
    emit(name, data) { this.sent.push([name, data]); return super.emit(name, data); }
}
const load = () => import('../src/browserSession.mjs');
const tick = ms => new Promise(resolve => setTimeout(resolve, ms));

test('opening starts a session; frames preserve their MIME type and commands target that session', async () => {
    const { connectBrowserView } = await load();
    const socket = new Socket(); let view;
    const client = connectBrowserView(socket, data => view = data);
    try {
        const id = socket.sent[0][1].session_id;
        assert.equal(socket.sent[0][0], 'start_web_browser');
        assert.equal(client.command({ action: 'reload' }), false);
        socket.emit('web_browser_frame', { session_id: id, image: 'abc', mime_type: 'image/png', url: 'https://example.com' });
        assert.equal(view.image, 'data:image/png;base64,abc');
        assert.equal(client.command({ action: 'reload' }), true);
        assert.deepEqual(socket.sent.at(-1), ['web_browser_command', { session_id: id, action: 'reload' }]);
    } finally { client.dispose(); }
    assert.equal(socket.listenerCount('web_browser_frame'), 0);
    assert.equal(socket.sent.at(-1)[0], 'stop_web_browser');
});

test('retry ignores late frames and reconnect starts a fresh session', async () => {
    const { connectBrowserView } = await load();
    const socket = new Socket(); let view;
    const client = connectBrowserView(socket, data => view = data);
    try {
        const old = socket.sent[0][1].session_id;
        client.retry();
        socket.emit('web_browser_frame', { session_id: old, image: 'stale' });
        assert.equal(view.image, null);
        socket.connected = false; socket.emit('disconnect');
        assert.equal(view.state, 'error');
        socket.connected = true; socket.emit('connect');
        assert.equal(socket.sent.at(-1)[0], 'start_web_browser');
        assert.notEqual(socket.sent.at(-1)[1].session_id, old);
    } finally { client.dispose(); }
});

test('startup and stalled streams time out visibly; server errors are retained', async () => {
    const { connectBrowserView } = await load();
    const socket = new Socket(); let view;
    const client = connectBrowserView(socket, data => view = data, { timeout: 15 });
    try {
        await tick(30);
        assert.equal(view.state, 'error');
        assert.match(view.message, /No browser frames/);
        client.retry();
        const id = socket.sent.at(-1)[1].session_id;
        socket.emit('web_browser_frame', { session_id: id, image: 'jpeg' });
        await tick(30);
        assert.equal(view.state, 'error');
        socket.emit('web_browser_status', { session_id: id, state: 'error', message: 'Install Chromium' });
        await tick(30);
        assert.equal(view.message, 'Install Chromium');
    } finally { client.dispose(); }
});
