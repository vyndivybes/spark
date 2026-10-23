'use strict';

const {pathToFileURL} = require('node:url');
const path = require('node:path');

// A portal in the same Electron process is never a substitute for the cockpit.
function selectCockpitTarget(targets, repo, backendPort) {
  const expected = pathToFileURL(path.resolve(repo, 'dist/index.html')).href;
  const matches = targets.filter(target => {
    if (target.type !== 'page') return false;
    try {
      const url = new URL(target.url);
      return url.protocol === 'file:' && url.href.split('?')[0] === expected
        && url.searchParams.get('sparkBackendPort') === String(backendPort);
    } catch { return false; }
  });
  if (matches.length !== 1) throw Error(`Expected one isolated SPARK cockpit; found ${matches.length}. Refusing portal fallback.`);
  return matches[0];
}

module.exports = {selectCockpitTarget};
