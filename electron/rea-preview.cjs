'use strict';
// Fixed recipe only. Third-party output is never evaluated as code.
const fs=require('node:fs/promises');
const path=require('node:path');
const crypto=require('node:crypto');
const {pathToFileURL}=require('node:url');
const {verifyBlueprintHtml,BLUEPRINT_TEST,BLUEPRINT_RELOAD_TEST}=require('./rea-blueprint.cjs');
function deadline(promise,ms=12000){let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Preview operation timed out.')),ms);})]).finally(()=>clearTimeout(timer));}
const hash=data=>crypto.createHash('sha256').update(data).digest('hex');
function identifiers(project,id){
 if(typeof project!=='string'||!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(project)||typeof id!=='string'||!/^[a-f0-9]{24}$/.test(id))throw Error('Invalid project or report.');
}
async function artifact(root,project,id){
 identifiers(project,id);
 const base=path.resolve(root),folder=path.join(base,'rea-workflows',project,id),file=path.join(folder,'app','index.html');
 for(const p of [base,path.join(base,'rea-workflows'),path.join(base,'rea-workflows',project),folder,path.join(folder,'app'),file,path.join(folder,'report.json')]){
  const st=await fs.lstat(p);if(st.isSymbolicLink())throw Error('Linked preview storage prohibited.');
 }
 const report=JSON.parse(await fs.readFile(path.join(folder,'report.json'),'utf8'));
 const bytes=await fs.readFile(file);
 if(!['notes','blueprint'].includes(report.recipe)||bytes.length>200000||hash(bytes)!==report.artifact_sha256)throw Error('App integrity check failed. Rebuild a new candidate.');
 return {folder,file,sha256:hash(bytes),recipe:report.recipe,source:bytes.toString('utf8')};
}
const BEHAVIOR_TEST=`(()=>{
 const $=id=>document.getElementById(id),checks=[];
 function check(name,ok){if(!ok)throw Error(name);checks.push(name);}
 function fill(id,value){$(id).value=value;$(id).dispatchEvent(new Event('input',{bubbles:true}));}
 localStorage.clear();
 $('folder-name').value='Flight';$('add-folder').click();
 check('create folder',[...$('folder').options].some(o=>o.value==='Flight'));
 $('add-note').click();fill('title','Flight plan');fill('body','Climb safely');
 $('note-folder').value='Flight';$('note-folder').dispatchEvent(new Event('change'));
 $('pin').click();check('pin note',$('pin').textContent==='Unpin');
 $('body').setSelectionRange(0,5);$('bold').click();check('bold formatting',!!document.querySelector('#preview strong'));
 $('body').setSelectionRange(8,14);$('italic').click();check('italic formatting',!!document.querySelector('#preview em'));
 fill('search','Flight');check('search matching note',$('notes').children.length===1);
 fill('search','no-such-note');check('search hides nonmatch',$('notes').children.length===0);
 fill('search','');$('folder').value='Flight';$('folder').dispatchEvent(new Event('change'));check('folder filter',$('notes').children.length===1);
 fill('body','<img src=x onerror=alert(1)>');check('untrusted text is not HTML',!document.querySelector('#preview img'));
 const saved=JSON.parse(localStorage.getItem('spark-original-notes-v1'));
 check('local persistence',saved.notes[0].title==='Flight plan'&&saved.notes[0].folder==='Flight'&&saved.notes[0].pinned);
 return checks;
})()`;
const RELOAD_TEST=`(()=>{if(document.getElementById('title').value!=='Flight plan')throw Error('reload persistence');window.confirm=()=>true;document.getElementById('delete').click();if(document.getElementById('notes').children.length)throw Error('delete note');return ['reload persistence','delete note'];})()`;
function createReaPreview({BrowserWindow,session,root,recipeFile,blueprintFile}){
 const windows=new Map();
 async function checked(project,id){
  const a=await artifact(root,project,id);
  // A manifest cannot authorize arbitrary local HTML: compare with shipped recipe too.
  if(a.recipe==='blueprint'){
   if(!blueprintFile)throw Error('The shipped blueprint renderer is unavailable.');
   verifyBlueprintHtml(a.source,await fs.readFile(blueprintFile,'utf8'));
  }else if(hash(await fs.readFile(recipeFile))!==a.sha256)throw Error('Only the shipped original recipe may run.');
  return a;
 }
 function windowFor(partition,show,file){
  const w=new BrowserWindow({show,width:1100,height:760,title:'SPARK original app',webPreferences:{partition,nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
  w.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  w.webContents.on('will-navigate',e=>e.preventDefault());
  w.webContents.on('will-attach-webview',e=>e.preventDefault());
  w.webContents.session.setPermissionRequestHandler((_wc,_p,callback)=>callback(false));
  w.webContents.session.webRequest.onBeforeRequest((details,callback)=>callback({cancel:details.url!==pathToFileURL(file).href}));
  return w;
 }
 return {
  async test(project,id){
   const a=await checked(project,id),partition='rea-test-'+crypto.randomBytes(12).toString('hex');
   const w=windowFor(partition,false,a.file);
   try{
    const errors=[];w.webContents.on('render-process-gone',()=>errors.push('renderer stopped'));
    await deadline(w.loadFile(a.file));
    const checks=await deadline(w.webContents.executeJavaScript(a.recipe==='blueprint'?BLUEPRINT_TEST:BEHAVIOR_TEST));
    await deadline(w.loadFile(a.file));
    checks.push(...await deadline(w.webContents.executeJavaScript(a.recipe==='blueprint'?BLUEPRINT_RELOAD_TEST:RELOAD_TEST)));
    if(errors.length)throw Error('Renderer failed.');
    const result={state:'passed',sha256:a.sha256,checks,checked_at:new Date().toISOString(),recipe:a.recipe,scope:'fixed first-party renderer behavioral checks; isolated Chromium profile; not full app semantics'};
    await fs.writeFile(path.join(a.folder,'browser-test.json'),JSON.stringify(result));return result;
   }finally{if(!w.isDestroyed())w.destroy();await deadline(session.fromPartition(partition).clearStorageData(),5000);}
  },
  async open(project,id){
   const a=await checked(project,id),proofFile=path.join(a.folder,'browser-test.json');
   const proofInfo=await fs.lstat(proofFile);if(proofInfo.isSymbolicLink()||proofInfo.size>100000)throw Error('Invalid browser test proof.');
   const proof=JSON.parse(await fs.readFile(proofFile,'utf8'));
   if(proof.state!=='passed'||proof.sha256!==a.sha256)throw Error('Pass hidden browser tests before opening.');
   const key=project+':'+id,old=windows.get(key);
   if(old&&!old.isDestroyed()){old.show();old.focus();return {state:'opened'};}
   const w=windowFor('persist:rea-'+project+'-'+id,true,a.file);windows.set(key,w);
   w.on('closed',()=>windows.delete(key));try{await deadline(w.loadFile(a.file));}catch(error){if(!w.isDestroyed())w.destroy();windows.delete(key);throw error;}return {state:'opened',id};
  }
 };
}
module.exports={artifact,identifiers,hash,BEHAVIOR_TEST,RELOAD_TEST,createReaPreview};
