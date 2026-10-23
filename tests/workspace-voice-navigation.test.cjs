const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');

test('voice workspace navigation opens the command center and selects the requested screen', () => {
  const app = read('src/App.jsx');
  const center = read('src/components/CommandCenter.jsx');
  assert.match(app, /socket\.on\('workspace_navigate'/);
  assert.match(app, /setShowWorkspace\(true\)/);
  assert.match(app, /requestedNavigation=\{workspaceNavigation\}/);
  assert.match(center, /requestedNavigation\?\.screen/);
  assert.match(center, /setPage\(requested\)/);
});

test('repository screen loads reports and reflects voice-approved staging', () => {
  const screens = read('src/components/SparkScreens.jsx');
  assert.match(screens, /page !== 'Repository Intelligence'/);
  assert.match(screens, /request\('list_repository_analyses'\)/);
  assert.match(screens, /socket\.on\('repository_voice_stage'/);
  assert.match(screens, /Testing and activation still require approval/);
});
