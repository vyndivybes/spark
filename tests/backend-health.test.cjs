const test = require('node:test');
const assert = require('node:assert/strict');
const { classifyBackendWait } = require('../electron/backend-health.cjs');

test('a live but slow backend is reported as starting, not offline', () => {
  const result = classifyBackendWait({ childAlive: true, elapsedMs: 20000 });
  assert.equal(result.state, 'starting');
  assert.equal(result.level, 'log');
  assert.match(result.message, /still starting/);
  assert.doesNotMatch(result.message, /offline/);
});

test('an exited or absent backend is reported offline', () => {
  const result = classifyBackendWait({ childAlive: false, elapsedMs: 20000 });
  assert.equal(result.state, 'offline');
  assert.equal(result.level, 'warn');
  assert.match(result.message, /core backend offline/);
});

test('the readiness check stays quiet before the wait window expires', () => {
  assert.equal(classifyBackendWait({ childAlive: true, elapsedMs: 1 }).state, 'waiting');
  assert.equal(classifyBackendWait({ childAlive: false, elapsedMs: 1 }).state, 'waiting');
});
