const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

test('intelligence console renders separate accessible pages and offline state without contacting a model',()=>{
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'spark-intelligence-ui-'));
  const target=path.join(directory,'console.cjs');
  try{
    esbuild.buildSync({entryPoints:[path.join(__dirname,'../src/components/IntelligenceConsole.jsx')],outfile:target,bundle:true,platform:'node',format:'cjs',external:['react'],logLevel:'silent'});
    const Module=require('node:module');
    const loaded=new Module(target,module);loaded.filename=target;loaded.paths=module.paths;
    loaded._compile(fs.readFileSync(target,'utf8'),target);
    const Component=loaded.exports.default;
    const html=renderToStaticMarkup(React.createElement(Component,{socket:{connected:false},project:'general'}));
    for(const page of ['Agents','Autonomy','Learning','Skills','Memory','Models','System health','Benchmarks','Integrations','Upgrades']) assert.ok(html.includes(page),page);
    assert.ok(html.includes('Backend offline'));
    assert.ok(html.includes('aria-label="Intelligence pages"'));
    assert.ok(!html.includes('success rate: 100'));
  }finally{fs.rmSync(directory,{recursive:true,force:true});}
});
