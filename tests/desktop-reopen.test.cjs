const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../electron/main.js'), 'utf8');

function secondInstance(window) {
  let handler, created = 0;
  const start = source.indexOf("app.on('second-instance'");
  const end = source.indexOf('let pythonProcess;', start);
  vm.runInNewContext(source.slice(start, end), {
    app: {on(event, callback) { handler = callback; }},
    mainWindow: window,
    createWindow() { created++; },
  });
  handler();
  return created;
}

test('clicking the icon recreates a missing or destroyed cockpit', () => {
  assert.equal(secondInstance(null), 1);
  assert.equal(secondInstance({isDestroyed: () => true}), 1);
});

test('clicking the icon restores and focuses an existing cockpit', () => {
  const calls = [];
  assert.equal(secondInstance({isDestroyed: () => false, isMinimized: () => true,
    restore() { calls.push('restore'); }, show() { calls.push('show'); },
    focus() { calls.push('focus'); }}), 0);
  assert.deepEqual(calls, ['restore', 'show', 'focus']);
});

test('closing the Windows cockpit quits even when side windows remain', () => {
  let closed, quits = 0;
  const start = source.indexOf("mainWindow.on('closed'");
  const end = source.indexOf('\n}', start);
  vm.runInNewContext(source.slice(start, end), {
    mainWindow: {on(event, callback) { closed = callback; }},
    app: {quit() { quits++; }}, process: {platform: 'win32'},
  });
  closed();
  assert.equal(quits, 1);
});
