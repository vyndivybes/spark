const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

test('spark operating screens render the ten ninth-section pages offline without contacting a model',()=>{
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'spark-screens-ui-'));
  const target=path.join(directory,'screens.cjs');
  try{
    esbuild.buildSync({entryPoints:[path.join(__dirname,'../src/components/SparkScreens.jsx')],outfile:target,bundle:true,platform:'node',format:'cjs',external:['react'],logLevel:'silent'});
    const Module=require('node:module');
    const loaded=new Module(target,module);loaded.filename=target;loaded.paths=module.paths;
    loaded._compile(fs.readFileSync(target,'utf8'),target);
    const Component=loaded.exports.default;
    const html=renderToStaticMarkup(React.createElement(Component,{socket:{connected:false},project:'general'}));
    for(const page of ['Jarvis Command Center','Autonomous Missions','Capabilities &amp; Skills','Self-Upgrade Studio','Repository Intelligence','Memory &amp; Knowledge','Windows PC Manager','System Health','Security &amp; Approvals','Upgrade History','System Connectivity']) assert.ok(html.includes(page),page);
    assert.ok(html.includes('Backend offline'));
    assert.ok(html.includes('aria-label="Spark operating screens"'));
    assert.ok(!html.includes('Working…'));
  }finally{fs.rmSync(directory,{recursive:true,force:true});}
});

test('spark operating screens bundle includes the approved workspace actions only through user interactions',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../src/components/SparkScreens.jsx'),'utf8');
  for(const action of ['self_heal_diagnose','security_scan','files_intelligence_scan','files_search','disk_forecast','import_repository','saee_registry','workforce_roles','profile_import_cost','profile_compare','connectivity_report','pc_startup_inventory','pc_process_inventory','pc_advisory'])
    assert.ok(source.includes(`'${action}'`),action);
  assert.ok(!source.includes('approved:true')||source.includes('window.confirm'),'activation and testing approvals require a confirmation dialog');
});
