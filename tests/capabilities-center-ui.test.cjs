'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

const read=file=>fs.readFileSync(path.join(__dirname,'..',file),'utf8');
const center=read('src/components/CapabilitiesCenter.jsx');
const panel=read('src/components/WorkspacePanel.jsx');

function render(componentFile, props) {
    const filename=path.join(__dirname,'..','src/components',componentFile);
    const build=esbuild.buildSync({entryPoints:[filename],bundle:true,write:false,platform:'node',format:'cjs',external:['react'],logLevel:'silent'});
    const Module=require('node:module');
    const loaded=new Module(filename,module);
    loaded.filename=filename; loaded.paths=module.paths;
    loaded._compile(build.outputFiles[0].text,filename);
    return renderToStaticMarkup(React.createElement(loaded.exports.default,props));
}

test('Capabilities Center renders sixteen labeled capability pages',()=>{
    const markup=render('CapabilitiesCenter.jsx',{socket:{connected:false},visible:true,project:'research'});
    for(const label of ['Capabilities Center','01 · Morning Digest','02 · WhatsApp Gateway',
        '03 · Proactive Agent','04 · OpenCode Agent','05 · Deep Research','06 · Messaging Hub',
        '07 · Trace Learning','08 · Spec Search','09 · Skill Ecosystem','10 · Agent Runtimes',
        '11 · Continuous Monitors','12 · Adaptive Routing','13 · Connector Catalog',
        '14 · Standardized Evaluations','15 · Inference Telemetry','16 · Inference Backends'])
        assert.ok(markup.includes(label),'Missing page label: '+label);
    assert.match(markup,/owner-gated workbench/);
});

test('Every page action is emitted through the owner-gated workspace handler',()=>{
    const actions=[...center.matchAll(/\{action:'([a-z_]+)'/g)].map(match=>match[1]);
    assert.ok(actions.length>=71,'Expected the full declared action surface');
    assert.ok(actions.every(action=>/[a-z_]+/.test(action)));
    assert.doesNotMatch(center,/fetch\(|axios|http:\/\/|https:\/\//);
    for(const wiring of ["socket.emit('workspace_action',","workspace_token:socket.workspaceToken",
        "request_id:`capabilities-${counter.current}`","socket.on('workspace_result'","if(!data.ok)"])
        assert.ok(center.includes(wiring),'Missing emit wiring: '+wiring);
});

test('WorkspacePanel navigation exposes Capabilities as its own tab',()=>{
    assert.ok(panel.includes("import CapabilitiesCenter from './CapabilitiesCenter';"));
    assert.ok(panel.includes(">Capabilities</button>") && panel.includes("tab==='capabilities'"));
    assert.ok(panel.includes("tab==='capabilities' ? <CapabilitiesCenter"));
});

test('Payload builder casts declared field types honestly',()=>{
    const compiled=esbuild.buildSync({entryPoints:[path.join(__dirname,'..','src/components/CapabilitiesCenter.jsx')],bundle:true,write:false,platform:'node',format:'cjs',external:['react'],logLevel:'silent'});
    const Module=require('node:module');
    const loaded=new Module('capabilities-test','.');
    loaded.paths=module.paths;
    loaded._compile(compiled.outputFiles[0].text,'capabilities-test');
    const {CAPABILITY_PAGES,buildPayload,summarizeStatus}=loaded.exports;
    const research=CAPABILITY_PAGES.find(page=>page.id==='deep-research');
    const payload=buildPayload(research.actions[0].fields,{question:'  vault notes  ',max_hops:'4'});
    assert.deepEqual(payload,{question:'  vault notes  ',max_hops:4});
    const digest=buildPayload([{key:'news_enabled',type:'bool',def:false}],
        {news_enabled:true});
    assert.deepEqual(digest,{news_enabled:true});
    const telemetry=buildPayload([{key:'latency_ms',type:'number',def:0},{key:'energy',type:'json',def:''}],
        {latency_ms:'250',energy:''});
    assert.deepEqual(telemetry,{latency_ms:250,energy:''});
    assert.throws(()=>buildPayload([{key:'manifest',type:'json',def:'{}'}],{manifest:'{bad'}));
    assert.ok(String(summarizeStatus({policy:'x',suites:[1,2,3]})).includes('suites: 3'));
});
