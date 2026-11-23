const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=part=>fs.readFileSync(path.resolve(__dirname,'..',part),'utf8');

test('VoiceStudio mode is opt-in, never changes default provider or starts external TTS',()=>{
 const launch=read('start-spark.ps1');
 const main=read('electron/main.js');
 assert.match(launch,/ValidateSet\('windows', 'voicestudio'\)/);
 assert.match(launch,/\$VoiceProvider = 'windows'/);
 assert.match(main,/process\.env\.SPARK_VOICE_PROVIDER==='voicestudio'/);
 assert.match(main,/sparkVoiceProvider:'voicestudio'/);
 assert.match(main,/createVoiceStudioClient\(\)\.render\(text\)/);
});

test('Electron IPC enforces owning cockpit identity before local VoiceStudio speech',()=>{
 const main=read('electron/main.js');
 const start=main.indexOf("ipcMain.handle('spark:voicestudio:render'");
 const end=main.indexOf("ipcMain.handle('spark:workspace-token'",start);
 assert.ok(start>0&&end>start);
 const handler=main.slice(start,end);
 assert.match(handler,/trustedWorkspaceSender\(event,mainWindow/);
 assert.match(handler,/VOICESTUDIO_COCKPIT_DENIED/);
 assert.doesNotMatch(handler,/shell\.open|writeFile|exec\(/);
});

test('VoiceStudio uses the owner-only speech acknowledgement and user mute state',()=>{
 const app=read('src/App.jsx');
 const backend=read('backend/spark_groq.py');
 assert.match(app,/new VoiceStudioSpeech/);
 assert.match(app,/socket\.emit\('browser_speech_done', \{error: failed\}\)/);
 assert.match(app,/isUserMuted: \(\) => userMutedRef\.current/);
 assert.match(backend,/timeout=180 if local_tts else 30/);
 assert.match(backend,/SPARK_VOICE_PROVIDER/);
});
