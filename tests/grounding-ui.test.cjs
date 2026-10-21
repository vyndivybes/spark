const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');

test('Live grounding source metadata reaches initiating cockpit without model-text trust',()=>{
 const spark=read('backend/spark.py');
 const server=read('backend/server.py');
 assert.match(spark,/getattr\(response\.server_content, "grounding_metadata", None\)/);
 assert.match(spark,/extract_grounding_sources\(metadata\)/);
 assert.match(spark,/self\.on_web_sources\(\{"sources": sources\}\)/);
 assert.match(server,/sio\.emit\('web_sources', payload, room=sid\)/);
});
test('source cards are clickable through restricted Electron shell, never via unsafe Electron navigation',()=>{
 const app=read('src/App.jsx');
 const chat=read('src/components/ChatModule.jsx');
 const electron=read('electron/main.js');
 assert.match(app,/socket\.on\('web_sources'/);
 assert.match(app,/socket\.off\('web_sources'\)/);
 assert.match(chat,/msg\.sources/);
 assert.match(chat,/onOpenSource\(source\.url\)/);
 assert.match(electron,/spark:open-grounding-source/);
 assert.match(electron,/shell\.openExternal/);
 assert.match(electron,/event\.sender\.id\s*!==\s*mainWindow\.webContents\.id/);
 assert.match(electron,/https:/);
});
test('search must require explicit launcher opt in and preserve hands-free default',()=>{
 const script=read('start-spark.ps1');
 assert.match(script,/\[switch\]\$EnableGoogleSearch/);
 assert.match(script,/SPARK_ENABLE_GOOGLE_SEARCH/);
 assert.match(script,/\$LiveProfile\s*=\s*'cinematic'/);
 assert.match(script,/\$AudioTransport\s*=\s*'browser_aec'/);
});
