const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {selectCockpitTarget} = require('../scripts/commissioning-target.cjs');
const repo = path.resolve('isolated-rc');
const cockpit = {type:'page',url:pathToFileURL(path.join(repo,'dist/index.html')).href+'?sparkBackendPort=8010'};
const portal = {type:'page',url:'https://vedm.vayushastr.workers.dev/#home'};

test('selects the isolated cockpit even when a portal appears first', () => {
  assert.equal(selectCockpitTarget([portal,cockpit],repo,8010),cockpit);
});
test('refuses portal-only, wrong checkout, wrong port, and ambiguous targets', () => {
  for (const targets of [[portal],[{...cockpit,url:cockpit.url.replace('8010','8000')}],
    [{...cockpit,url:pathToFileURL(path.resolve('original/dist/index.html')).href+'?sparkBackendPort=8010'}],
    [cockpit,cockpit]]) {
    assert.throws(() => selectCockpitTarget(targets,repo,8010), /Refusing portal fallback/);
  }
});
