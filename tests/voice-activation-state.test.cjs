const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../src/App.jsx'), 'utf8');

test('voice activation does not falsely report microphone unmuted while connecting', () => {
  const begin = source.indexOf('const activateSparkCore = () => {');
  const end = source.indexOf('const openExperience = async', begin);
  assert.ok(begin >= 0 && end > begin);
  const fn = source.slice(begin, end);
  assert.doesNotMatch(fn, /setIsConnected\(true\);\s*setIsMuted\(false\)/);
  assert.match(fn, /activationPendingRef\.current = liveState\.state !== 'connected'/);
});

test('Gemini connection event, not socket connection, resumes audio after activation', () => {
  assert.match(source, /info\.state === 'connected'[\s\S]*?activationPendingRef\.current[\s\S]*?socket\.emit\('resume_audio'\)/);
  assert.match(source, /info\.state === 'connected'[\s\S]*?setIsMuted\(false\)/);
});
