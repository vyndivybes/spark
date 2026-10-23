const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');const os=require('node:os');
const esbuild=require('esbuild');const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
test('voice glow uses approved session events and exact graph node palette without SpeechRecognition',()=>{
 const values={};const scope={window:{},document:{documentElement:{style:{setProperty:(key,value)=>values[key]=value}}}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/voicePulse.js'),'utf8'),scope);
 scope.window.updateNodeType('project');assert.equal(values['--spark-pulse-color'],'#f87171');
 scope.window.sparkVoicePulse();assert.equal(values['--spark-pulse-color'],'#f87171');
});
test('full Python forge renders policy, imports/API execution controls and stop actions',()=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'spark-python-forge-'));
 try{
  const target=path.join(directory,'forge.cjs');esbuild.buildSync({entryPoints:[path.join(__dirname,'../src/components/PythonToolForge.jsx')],outfile:target,bundle:true,platform:'node',format:'cjs',external:['react'],logLevel:'silent'});
  const Module=require('node:module');const loaded=new Module(target,module);loaded.filename=target;loaded.paths=module.paths;loaded._compile(fs.readFileSync(target,'utf8'),target);
  const html=renderToStaticMarkup(React.createElement(loaded.exports.default,{socket:{connected:false},project:'default'}));
  assert.match(html,/Enable automatic invention/);assert.match(html,/Stop Python tools/);assert.match(html,/Stop background patching/);assert.match(html,/not confined to a security sandbox/);
 }finally{fs.rmSync(directory,{recursive:true,force:true});}
});
