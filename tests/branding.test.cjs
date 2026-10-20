'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const sourceDirectories = ['backend', 'src', 'electron', 'scripts', 'tests', 'public'];
const extensions = new Set([
  '.py', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx',
  '.html', '.css', '.json', '.md', '.ps1', '.yml', '.yaml', '.toml', '.txt'
]);
const forbidden = /ada_v2|ADA_V2|ADA[ -]V2|A\.D\.A|Hello Ada|Nazir Louis/g;
const skipDirs = new Set(['node_modules', '.venv', '.git', 'dist', 'build', '__pycache__', 'vendor', 'projects']);
const skipFiles = new Set(['branding.test.cjs', 'LICENSE', 'THIRD_PARTY_NOTICES.md']);

function* walk(dir) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!skipDirs.has(entry.name)) yield* walk(full);
    } else if (entry.isFile() && !skipFiles.has(entry.name) && extensions.has(path.extname(entry.name))) {
      yield full;
    }
  }
}

test('SPARK first-party sources and README have no legacy product branding', () => {
  const files = [
    ...sourceDirectories.flatMap(name => [...walk(path.join(root, name))]),
    ...fs.readdirSync(root, {withFileTypes: true})
      .filter(item => item.isFile() && !skipFiles.has(item.name) && extensions.has(path.extname(item.name)))
      .map(item => path.join(root, item.name))
  ];
  const failures = [];
  for (const filename of files) {
    const body = fs.readFileSync(filename, 'utf8');
    const matches = [...body.matchAll(forbidden)];
    if (matches.length) {
      failures.push(path.relative(root, filename) + ': ' + matches.length + ' occurrence(s)');
    }
  }
  assert.deepEqual(failures, [], 'Legacy branding remains in these files:\n' + failures.join('\n'));
});
