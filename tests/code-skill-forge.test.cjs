const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
test('code forge exposes generation, REA evidence, review and input controls',()=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'spark-code-forge-'));
 try {
  const target=path.join(directory,'forge.cjs');
  esbuild.buildSync({entryPoints:[path.join(__dirname,'../src/components/CodeSkillForge.jsx')],outfile:target,bundle:true,platform:'node',format:'cjs',external:['react'],logLevel:'silent'});
  const Module=require('node:module');const loaded=new Module(target,module);
  loaded.filename=target;loaded.paths=module.paths;loaded._compile(fs.readFileSync(target,'utf8'),target);
  const html=renderToStaticMarkup(React.createElement(loaded.exports.default,{socket:{connected:false},project:'default'}));
  for(const label of ['Code skill goal','Repository analysis ID','REA evidence ID','REA inspection arguments','Code skill specification'])assert.ok(html.includes(label));
  assert.match(html,/Generate candidate/);assert.match(html,/Inspect and retain evidence/);
  assert.match(html,/Passing generated examples proves those examples only/);
 }finally{fs.rmSync(directory,{recursive:true,force:true});}
});
