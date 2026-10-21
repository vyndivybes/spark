const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

test('command dashboard distinguishes offline, backend connected, and AI ready states', () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'spark-command-test-'));
    try {
        const target = path.join(directory, 'command.cjs');
        esbuild.buildSync({entryPoints:[path.join(__dirname, '../src/components/CommandCenter.jsx')], outfile:target, bundle:true, platform:'node', format:'cjs', external:['react'], logLevel:'silent'});
        const Module = require('node:module');
        const loaded = new Module(target, module);
        loaded.filename = target; loaded.paths = module.paths;
        loaded._compile(fs.readFileSync(target, 'utf8'), target);
        const Component = loaded.exports.default;
        const render = props => renderToStaticMarkup(React.createElement(Component, {socket:{connected:false}, project:'test-project', muted:true, ...props}));
        const offline = render({connected:false});
        assert.match(offline, /No backend connection/);
        assert.match(offline, /Connect core for readings/);
        assert.match(offline, /A fresh starting point/);
        assert.doesNotMatch(offline, /AI session ready/);
        for (const name of ['Missions', 'Knowledge', 'Memory', 'Upgrade studio', 'Repositories', 'PC manager', 'Connections', 'Approvals', 'History', 'Workbench']) assert.ok(offline.includes(name), name);
        const connected = render({connected:true, liveState:{state:'idle'}, diagnostics:{host:{cpu_percent:17.4, ram_percent:58.9}}});
        assert.match(connected, /17%/);
        assert.match(connected, /59%/);
        assert.match(connected, /AI session idle/);
        assert.doesNotMatch(connected, /AI session ready/);
        const ready = render({connected:true, liveState:{state:'connected'}, messages:[{sender:'user', text:'Inspect the project'}]});
        assert.match(ready, /AI session ready/);
        assert.match(ready, /Inspect the project/);
        assert.doesNotMatch(ready, /A fresh starting point/);
    } finally {fs.rmSync(directory, {recursive:true, force:true});}
});
