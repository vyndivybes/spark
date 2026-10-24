const test = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {showDigestNotification} = require('../electron/digest-notify.cjs');

test('delivery requires the native show event and the banner contains no task contents', async () => {
  let instance;
  class Notification extends EventEmitter {
    static isSupported() { return true; }
    constructor(options) { super(); this.options = options; instance = this; }
    show() { queueMicrotask(() => this.emit('show')); }
  }
  const result = await showDigestNotification({Notification, payload: {date: '2026-10-23', partial: false}});
  assert.equal(result.state, 'shown');
  assert.equal(result.ok, true);
  assert.equal(instance.options.title, 'SPARK Morning Digest');
  assert.equal(instance.options.silent, true);
  assert.match(instance.options.body, /Open SPARK/);
});

test('unsupported notifications and native failures do not report delivery', async () => {
  class Unsupported { static isSupported() { return false; } }
  assert.equal((await showDigestNotification({Notification: Unsupported,
    payload: {date: '2026-10-23', partial: true}})).ok, false);
  class Failure extends EventEmitter {
    static isSupported() { return true; }
    show() { queueMicrotask(() => this.emit('failed')); }
  }
  assert.equal((await showDigestNotification({Notification: Failure,
    payload: {date: '2026-10-23', partial: true}})).state, 'failed');
});

test('Electron bootstrap starts the notifier even when require.main is different', () => {
  const filename = path.resolve(__dirname, '../electron/digest-notify.cjs');
  let started = false;
  const app = {setPath() {}, setAppUserModelId() {}, whenReady() {
    started = true;
    return {then() {}};
  }};
  const req = name => name === 'electron' ? {app} : require(name);
  req.main = {};
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'), {
    require: req, module: {exports: {}}, __filename: filename,
    process: {versions: {electron: '28.2.0'}, type: 'browser',
      argv: ['electron.exe', filename, '2026-10-24', 'complete'], env: {LOCALAPPDATA: 'C:\\local'}},
  });
  assert.equal(started, true);
});
