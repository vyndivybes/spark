const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const src=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');

test('diagnostic text whitelists data and omits secrets / conversation',async()=>{
 const {formatHealthReport}=await import(pathToFileURL(path.join(__dirname,'../src/utils/sessionTools.mjs')));
 const message=formatHealthReport({
   ai_provider:'groq',live_state:'connected',live_model:'llama-3.1-8b-instant',
   audio_transport:'browser_aec',hands_free_ready:true,uptime_seconds:135,
   groq_configured:true,live_error_code:'429',
   api_key:'DO_NOT_LEAK',chat_history:'PRIVATE_USER_MESSAGE',token:'SECRET'
 });
 assert.match(message,/Groq/i);assert.match(message,/AEC.*ready/i);
 assert.match(message,/429/);assert.match(message,/135/);
 assert.doesNotMatch(message,/DO_NOT_LEAK|PRIVATE_USER_MESSAGE|SECRET|api_key/i);
});
test('session exporter honors sources but rejects unsafe links and bounds content',async()=>{
 const {formatTranscript}=await import(pathToFileURL(path.join(__dirname,'../src/utils/sessionTools.mjs')));
 const report=formatTranscript([
   {sender:'You',time:'02:10',text:'Explain what you see'},
   {sender:'ADA',time:'02:11',text:'A working assistant.'},
   {sender:'Search Sources',text:'Research results',
      sources:[{title:'Nasa',url:'https://www.nasa.gov/'},
               {title:'Bad',url:'javascript:alert(1)'},
               {title:'Secret URL',url:'https://u:p@example.com'}]}
 ],new Date('2026-10-18T02:47:00Z'));
 assert.match(report,/SPARK session transcript/);
 assert.match(report,/Explain what you see/);
 assert.match(report,/https:\/\/www\.nasa\.gov\//);
 assert.doesNotMatch(report,/javascript:|https:\/\/u:p/);
 assert.ok(formatTranscript(Array.from({length:600},()=>({sender:'You',text:'a'.repeat(9000)}))).length<=210000);
});
test('system center is wired to session-owner safe socket diagnostics',()=>{
 const backend=src('backend/server.py');
 const app=src('src/App.jsx');
 const ui=src('src/components/SystemCenter.jsx');
 const electron=src('electron/main.js');
 assert.match(backend,/async def get_diagnostics\(sid\):/);
 assert.match(backend,/sio\.emit\('spark_diagnostics', .*room=sid\)/);
 assert.match(app,/socket\.on\('spark_diagnostics'/);
 assert.match(app,/socket\.off\('spark_diagnostics'\)/);
 assert.match(app,/socket\.emit\('get_diagnostics'\)/);
 assert.match(app,/Ctrl\+Shift\+M/);
 assert.match(app,/ipcRenderer\.invoke\('spark:save-transcript'/);
 assert.match(ui,/Save transcript/i);
 assert.match(ui,/Copy report/i);
 assert.match(electron,/spark:save-transcript/);
 assert.match(electron,/dialog\.showSaveDialog/);
 assert.match(electron,/event\.sender\.id !== mainWindow\.webContents\.id/);
});
