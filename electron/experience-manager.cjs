'use strict';
// SPARK experience bridge: launch upstream MIT-licensed apps unchanged, on loopback.
// Never accept AI-generated process names, shell text, URLs or filesystem paths.
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const http = require('node:http');
const {spawn,spawnSync} = require('node:child_process');

const KNOWN = Object.freeze({holo:4890,brain:4710,vayu:4891});

function getExperiencePlan(name,{root,userData,python='python',notesDir,vayuExportsDir}={}){
  if(!Object.prototype.hasOwnProperty.call(KNOWN,name))throw new Error('Unknown SPARK experience.');
  if(!root||!userData||typeof python!=='string'||!python.trim())throw new Error('SPARK experience paths are unavailable.');
  const vendor=path.join(root,'vendor');
  if(name==='vayu'){
    const folder=path.join(vendor,'vayu-workspace');
    const wrapper=path.join(root,'scripts','vayu_launcher.py');
    if(!fs.existsSync(path.join(folder,'start.py'))||!fs.existsSync(wrapper))throw new Error('The bundled VAYU workspace or launcher is missing. Restore the SPARK checkout.');
    return {name,port:KNOWN.vayu,url:'http://127.0.0.1:'+KNOWN.vayu,
      page:'/VAYU-Knowledge-Sphere-Live.html',steps:[
        {command:python,args:[wrapper,'--port',String(KNOWN.vayu),'--data-dir',path.join(userData,'vayu-workspace')],cwd:folder,shell:false,once:false,
          env:{SPARK_VAYU_EXPORTS_DIR:vayuExportsDir||path.join(userData,'vayu-exports')}}
      ]};
  }
  const folder=path.join(vendor,name==='holo'?'holo-gestures':'brain-map');
  const script=path.join(folder,name==='holo'?'server.py':'build.py');
  if(!fs.existsSync(script))throw new Error('Experience files are missing. Run npm run setup:experiences from your SPARK checkout.');
  const port=KNOWN[name];
  const requestedVault=notesDir||path.join(vendor,'holo-gestures','sample-notes');
  const vault=fs.existsSync(requestedVault)&&fs.statSync(requestedVault).isDirectory()
    ? requestedVault:path.join(vendor,'holo-gestures','sample-notes');
  if(name==='holo'){
    const wrapper=path.join(root,'scripts','holo_notes_launcher.py');
    if(!fs.existsSync(wrapper))throw new Error('The SPARK HOLO notes launcher is missing.');
    return {name,port,url:'http://127.0.0.1:'+port,steps:[
      {command:python,args:[wrapper],cwd:folder,shell:false,once:false,
       env:{SPARK_HOLO_NOTES_DIR:vault}}
    ]};
  }
  if(!fs.existsSync(vault)||!fs.statSync(vault).isDirectory())throw new Error('A readable local Markdown notes folder is required for Brain Map.');
  const out=path.join(userData,'spark-brain-map');
  return {name,port,url:'http://127.0.0.1:'+port,steps:[
    {command:python,args:[script,'--vault',vault,'--out',out],cwd:folder,shell:false,once:true},
    {command:python,args:['-m','http.server',String(port),'--bind','127.0.0.1','--directory',out],cwd:out,shell:false,once:false}
  ]};
}

function assertPortFree(port){return new Promise((resolve,reject)=>{
  const s=net.createServer();
  s.once('error',()=>reject(new Error('Local experience port '+port+' is already occupied. Close the other app before opening SPARK experience.')));
  s.listen(port,'127.0.0.1',()=>s.close(resolve));
});}
function waitForServer(port,child,timeoutMs=10000,page='/'){return new Promise((resolve,reject)=>{
  const deadline=Date.now()+timeoutMs;
  const attempt=()=>{
    if(child.exitCode!==null||child.signalCode!==null)return reject(new Error('Local experience exited before it became ready.'));
    const req=http.get({host:'127.0.0.1',port,path:page,timeout:800},res=>{
      res.resume();
      if(res.statusCode===200)return resolve();
      if(Date.now()>=deadline)return reject(new Error('Local experience health check failed.'));
      setTimeout(attempt,150);
    });
    req.on('error',()=>Date.now()>=deadline?reject(new Error('Local experience did not become ready.')):setTimeout(attempt,150));
    req.on('timeout',()=>req.destroy());
  };
  attempt();
});}
// The upstream Brain Map builder prints ✓ and →. Windows Python may use a
// legacy CP1252 codec for redirected stdout; force UTF-8 for subprocesses.
// This is scoped to SPARK children, not the user's system Python settings.
function experiencePythonEnvironment(base=process.env){
  return {...base,PYTHONIOENCODING:'utf-8',PYTHONUTF8:'1'};
}
function formatBuildFailure(stderr){
  const lines=String(stderr||'').split(/\r?\n/).map(line=>line.trim()).filter(Boolean);
  const exception=lines.slice(-5).join(' | ');
  return (exception||'No Python traceback was returned.').slice(-600);
}
function completedProcess(step){return new Promise((resolve,reject)=>{
  const child=spawn(step.command,step.args,{
    cwd:step.cwd,shell:false,windowsHide:true,env:experiencePythonEnvironment(),
    stdio:['ignore','ignore','pipe']
  });
  let error='';
  child.stderr.on('data',buf=>{if(error.length<16384)error+=String(buf).slice(0,16384-error.length);});
  child.once('error',()=>reject(new Error('Unable to start the configured Python interpreter.')));
  child.once('close',code=>code===0?resolve():reject(new Error(
    'Brain Map could not build its local graph (exit '+code+'). '+formatBuildFailure(error))));
});}
function killOwnedProcess(child){
  if(!child||!child.pid)return;
  if(process.platform==='win32'){
    spawnSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,timeout:3000,stdio:'ignore'});
  }else{try{child.kill('SIGTERM')}catch{}}
}
function createExperienceManager({root,userData,python='python',notesDir,vayuExportsDir,BrowserWindow}){
  const windows=new Map(),children=new Map();
  async function open(name){
    if(!BrowserWindow)throw new Error('Windows experience hosting is unavailable.');
    if(windows.has(name)&&!windows.get(name).isDestroyed()){
      windows.get(name).focus();return {opened:true,reused:true,experience:name};
    }
    const plan=getExperiencePlan(name,{root,userData,python,notesDir,vayuExportsDir});
    await assertPortFree(plan.port);
    for(const step of plan.steps){
      if(step.once){fs.mkdirSync(path.dirname(step.args[step.args.indexOf('--out')+1]),{recursive:true});await completedProcess(step);continue;}
      const child=spawn(step.command,step.args,{cwd:step.cwd,shell:false,windowsHide:true,stdio:'ignore',
        env:experiencePythonEnvironment({...process.env,...(step.env||{})})});
      children.set(name,child);
      const failedToStart=new Promise((_,reject)=>child.once('error',()=>reject(new Error('Python is unavailable. Configure SPARK_PYTHON or install Python.'))));
      try{await Promise.race([waitForServer(plan.port,child,10000,plan.page),failedToStart]);}
      catch(e){killOwnedProcess(child);children.delete(name);throw e;}
    }
    const win=new BrowserWindow({width:1450,height:910,backgroundColor:'#070b13',title:name==='vayu'?'SPARK · VAYU WORKSPACE':name==='holo'?'SPARK · HOLO DECK':'SPARK · NEURAL ATLAS',
      webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
    win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
    win.webContents.on('will-navigate',(event,url)=>{if(!url.startsWith(plan.url+'/'))event.preventDefault();});
    windows.set(name,win);
    win.on('closed',()=>{windows.delete(name);killOwnedProcess(children.get(name));children.delete(name);});
    try{await win.loadURL(plan.url+(plan.page||''));}catch(e){win.close();throw new Error('SPARK experience could not load its local interface.');}
    return {opened:true,reused:false,experience:name};
  }
  function stopAll(){for(const win of windows.values())if(!win.isDestroyed())win.close();for(const child of children.values())killOwnedProcess(child);windows.clear();children.clear();}
  return {open,stopAll};
}
module.exports={getExperiencePlan,createExperienceManager,experiencePythonEnvironment,formatBuildFailure};
