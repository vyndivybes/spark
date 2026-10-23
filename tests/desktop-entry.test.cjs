const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('a repeated desktop launch exits before creating another backend or window', () => {
  let quit = false;
  const app = {
    requestSingleInstanceLock:() => false,
    quit:() => {quit = true;},
    whenReady:() => {throw Error('Secondary instance attempted startup');},
  };
  const sandbox = {
    process:{env:{}},
    require:name => name === 'electron' ? {app} : name === 'node:crypto'
      ? {randomBytes:() => Buffer.alloc(32)} : {},
    console,
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../electron/main.js'), 'utf8'), sandbox);
  assert.equal(quit, true);
});
