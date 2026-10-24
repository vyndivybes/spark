// Run with Electron, not Node. Creates only a temporary test workspace.
const fsSync=require('node:fs');
const log=process.env.SPARK_REA_SMOKE_LOG;
if(log){console.log=(...args)=>fsSync.appendFileSync(log,args.join(' ')+'\n');console.error=console.log;}
console.log('SMOKE START');
const {app,BrowserWindow,session}=require('electron');
console.log('ELECTRON API LOADED');
app.on('window-all-closed',()=>console.log('TEST WINDOWS CLOSED; acceptance continues'));
app.on('before-quit',()=>console.log('BEFORE QUIT'));
process.on('uncaughtException',error=>{console.error('UNCAUGHT',error.stack);app.exit(1);});
process.on('unhandledRejection',error=>{console.error('REJECTION',String(error));app.exit(1);});
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {createReaPreview,hash}=require('../electron/rea-preview.cjs');
app.commandLine.appendSwitch('disable-gpu');
console.log('WAITING FOR ELECTRON READY');
app.whenReady().then(async()=>{
 console.log('ELECTRON READY');
 let root;
 try{
  root=await fs.mkdtemp(path.join(os.tmpdir(),'spark-rea-browser-'));
  const id='b'.repeat(24),folder=path.join(root,'rea-workflows','default',id);
  await fs.mkdir(path.join(folder,'app'),{recursive:true});
  const recipeFile=path.resolve(__dirname,'../backend/spark_rea_notes.html'),source=await fs.readFile(recipeFile);
  await fs.writeFile(path.join(folder,'app','index.html'),source);
  await fs.writeFile(path.join(folder,'report.json'),JSON.stringify({recipe:'notes',artifact_sha256:hash(source)}));
  const preview=createReaPreview({BrowserWindow:function(options){return new BrowserWindow({...options,show:false});},session,root,recipeFile});
  let refused=false;try{await preview.open('default',id);}catch{refused=true;}
  if(!refused)throw Error('Untested app was allowed to launch');
  console.log('STARTING HIDDEN BROWSER CHECKS');
  const result=await preview.test('default',id);
  if(result.state!=='passed'||result.checks.length<10)throw Error('Missing behavioral coverage');
  console.log(JSON.stringify({state:'PASS',launch_before_test:'refused',...result}));
  // Exercise the launch path without leaving a window on the owner desktop.
  const opened=await preview.open('default',id);
  if(opened.state!=='opened')throw Error('Tested app launch failed');
  for(const w of BrowserWindow.getAllWindows())w.destroy();
  console.log('TESTED APP LAUNCH PASS');
  app.exit(0);
 }catch(e){console.error(e.stack);app.exit(1);}
});
setTimeout(()=>{console.error('Browser smoke timed out');app.exit(2);},45000);


