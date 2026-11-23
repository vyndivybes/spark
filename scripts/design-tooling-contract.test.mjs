import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = new URL('../', import.meta.url);
const config = JSON.parse(readFileSync(new URL('../opencode.json', import.meta.url), 'utf8'));
const guide = readFileSync(new URL('../docs/development/stitch-chrome-devtools.md', import.meta.url), 'utf8');
const skill = readFileSync(new URL('../.agents/skills/stitch-design-workflow/SKILL.md', import.meta.url), 'utf8');

test('Chrome DevTools MCP remains isolated, telemetry opt-out and dev-only', () => {
  const chrome = config.mcp['chrome-devtools'];
  assert.equal(chrome.type, 'local');
  assert.equal(chrome.enabled, true);
  assert.equal(chrome.command[0], 'npx');
  assert.ok(chrome.command.includes('chrome-devtools-mcp@1.13.0'));
  for (const required of ['--isolated', '--no-usage-statistics', '--no-performance-crux']) {
    assert.ok(chrome.command.includes(required), required);
  }
  assert.ok(guide.includes('not a production browser'));
});

test('Stitch requires a local authenticated endpoint and is not enabled by default', () => {
  const stitch = config.mcp.stitch;
  assert.equal(stitch.type, 'remote');
  assert.equal(stitch.enabled, false);
  assert.equal(stitch.url, '{env:STITCH_MCP_URL}');
  assert.ok(guide.includes('stitch.withgoogle.com/docs/mcp/setup/'));
  assert.ok(skill.includes('**HOLD**'));
});

test('Design skill preserves approval gates and existing tests', () => {
  assert.ok(skill.startsWith('---\nname: stitch-design-workflow'));
  assert.ok(skill.includes('Founder approval'));
  assert.ok(skill.includes('Playwright'));
  assert.ok(guide.includes('node --test scripts/design-tooling-contract.test.mjs'));
});
