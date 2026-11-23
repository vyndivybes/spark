import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const config = JSON.parse(read('opencode.json'));

test('SPARK keeps its zero-cost OmniRoute model configuration', () => {
  assert.match(config.model, /:free$/);
  assert.match(config.small_model, /:free$/);
  assert.equal(config.shell, 'powershell.exe');
});

test('Chrome DevTools remains an isolated development-only browser', () => {
  const chrome = config.mcp['chrome-devtools'];
  assert.equal(chrome.type, 'local');
  assert.equal(chrome.enabled, true);
  for (const arg of ['--isolated', '--no-usage-statistics', '--no-performance-crux']) {
    assert.ok(chrome.command.includes(arg), arg);
  }
  assert.ok(!chrome.command.some((arg) => /^--(?:browserUrl|browser-url|wsEndpoint|ws-endpoint)/.test(arg)));
});

test('Plannotator and Stitch are disabled unless a developer authorizes setup', () => {
  assert.equal(config.mcp.plannotator.type, 'local');
  assert.deepEqual(config.mcp.plannotator.command, ['plannotator', 'inbox', 'mcp']);
  assert.equal(config.mcp.plannotator.enabled, false);
  assert.equal(config.mcp.stitch.enabled, false);
  assert.equal(config.mcp.stitch.url, '{env:STITCH_MCP_URL}');
});

test('new MCP entry has no cloud URL, external token or auto-activation', () => {
  const plannotator = JSON.stringify(config.mcp.plannotator);
  assert.doesNotMatch(plannotator, /(?:https?:|API_KEY|SECRET|TOKEN|OPENAI)/i);
  assert.ok(config.mcp.Neon.enabled === false);
  assert.deepEqual(Object.entries(config.mcp).filter(([name, mcp]) => name !== 'chrome-devtools' && mcp.enabled), []);
});

for (const [name, repo] of [
  ['modern-web-guidance-governed', 'GoogleChrome/modern-web-guidance'],
  ['plannotator-review', 'backnotprop/plannotator'],
  ['open-code-review-delegate', 'alibaba/open-code-review'],
  ['cloudflare-security-audit', 'cloudflare/security-audit-skill'],
]) {
  test(name + ' is discoverable and has explicit upstream origin and HOLD gate', () => {
    const skill = read('.agents/skills/' + name + '/SKILL.md');
    assert.ok(skill.startsWith('---\nname: ' + name + '\n'));
    assert.ok(skill.includes('https://github.com/' + repo));
    assert.ok(skill.includes('HOLD'));
    assert.match(skill, /approval/i);
  });
}

test('delegated review does not require a separate paid LLM API token', () => {
  const skill = read('.agents/skills/open-code-review-delegate/SKILL.md');
  assert.match(skill, /ocr delegate preview/);
  assert.match(skill, /ocr delegate rule/);
  assert.match(skill, /no separate API key/);
  assert.doesNotMatch(skill, /ocr review --from/);
});

test('security auditing is sandboxed, independent and never silently passed', () => {
  const skill = read('.agents/skills/cloudflare-security-audit/SKILL.md');
  assert.match(skill, /independent verifier/i);
  assert.match(skill, /sandbox/i);
  assert.match(skill, /needs_validation/);
});

test('the instructions protect local SPARK and external business action gates', () => {
  const guide = read('docs/development/spark-governed-agent-toolchain.md');
  assert.match(guide, /development-only/);
  assert.match(guide, /C:\\Users\\ASUS\\spark/);
  assert.match(guide, /not an automated deployment/);
  assert.match(guide, /founder approval/);
  assert.match(guide, /uncommitted changes/);
});
