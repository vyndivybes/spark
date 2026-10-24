const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {artifact,hash,identifiers}=require('../electron/rea-preview.cjs');
test('preview verifies artifact digest and refuses tampering',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'spark-rea-proof-'));
 try{
  const id='a'.repeat(24),folder=path.join(root,'rea-workflows','default',id),app=path.join(folder,'app','index.html');
  await fs.mkdir(path.dirname(app),{recursive:true});await fs.writeFile(app,'original');
  await fs.writeFile(path.join(folder,'report.json'),JSON.stringify({recipe:'notes',artifact_sha256:hash('original')}));
  assert.equal((await artifact(root,'default',id)).sha256,hash('original'));
  await fs.writeFile(app,'changed');await assert.rejects(()=>artifact(root,'default',id),/integrity/);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
test('preview identifiers cannot escape workspace',()=>{
 assert.throws(()=>identifiers('../escape','a'.repeat(24)));
 assert.throws(()=>identifiers('default','../index.html'));
 identifiers('default','a'.repeat(24));
});

test('only shipped recipes run; untested and stale proof cannot open a window',async()=>{
 const {createReaPreview}=require('../electron/rea-preview.cjs');
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'spark-rea-launch-'));
 try{
  const id='b'.repeat(24),folder=path.join(root,'rea-workflows','default',id),app=path.join(folder,'app','index.html'),recipe=path.join(root,'recipe.html');
  await fs.mkdir(path.dirname(app),{recursive:true});await fs.writeFile(recipe,'shipped');await fs.writeFile(app,'shipped');
  await fs.writeFile(path.join(folder,'report.json'),JSON.stringify({recipe:'notes',artifact_sha256:hash('shipped')}));
  let calls=0;
  const preview=createReaPreview({root,recipeFile:recipe,BrowserWindow:function(){calls++;throw Error('Unexpected browser launch');},session:{}});
  await assert.rejects(()=>preview.open('default',id));assert.equal(calls,0);
  await fs.writeFile(path.join(folder,'browser-test.json'),JSON.stringify({state:'passed',sha256:hash('old')}));
  await assert.rejects(()=>preview.open('default',id),/Pass hidden browser/);assert.equal(calls,0);
  await fs.writeFile(app,'arbitrary script');await fs.writeFile(path.join(folder,'report.json'),JSON.stringify({recipe:'notes',artifact_sha256:hash('arbitrary script')}));
  await assert.rejects(()=>preview.test('default',id),/shipped original recipe/);assert.equal(calls,0);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
