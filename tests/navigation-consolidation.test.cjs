const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

function renderComponent(file, props) {
    const filename = path.resolve(__dirname, '../src/components', file);
    const build = esbuild.buildSync({entryPoints:[filename], bundle:true, write:false, platform:'node', format:'cjs', external:['react'], logLevel:'silent'});
    const Module = require('node:module');
    const loaded = new Module(filename, module);
    loaded.filename = filename;
    loaded.paths = module.paths;
    loaded._compile(build.outputFiles[0].text, filename);
    return renderToStaticMarkup(React.createElement(loaded.exports.default, props));
}

test('embedded workspace has no competing navigation or unrelated publishing actions', () => {
    const props = {socket:{connected:false}, visible:true, project:'default', embedded:true, initialTab:'knowledge'};
    const knowledge = renderComponent('WorkspacePanel.jsx', props);
    assert.doesNotMatch(knowledge, /role="tablist"|SPARK HOME/);
    assert.match(knowledge, /Search project knowledge/);
    assert.match(knowledge, /Search synchronized sources/);
    assert.doesNotMatch(knowledge, /Publish \/ refresh VAYU snapshot/);
    const skills = renderComponent('WorkspacePanel.jsx', {...props, initialTab:'skills'});
    assert.doesNotMatch(skills, /VAYU snapshot|role="tablist"/);
});

test('embedded intelligence keeps its selected page without a second sidebar', () => {
    const props = {socket:{connected:false}, project:'default', initialPage:'Memory', compactNavigation:true};
    const embedded = renderComponent('IntelligenceConsole.jsx', props);
    assert.doesNotMatch(embedded, /aria-label="Intelligence pages"/);
    const standalone = renderComponent('IntelligenceConsole.jsx', {...props, compactNavigation:false});
    assert.match(standalone, /aria-label="Intelligence pages"/);
});
