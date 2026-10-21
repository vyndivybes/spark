const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname,'..');
const read = p => fs.readFileSync(path.join(root,p),'utf8');

test('large raw PCM arrays are not serialized to Socket.IO solely for animations',()=>{
 const server=read('backend/server.py');
 const app=read('src/App.jsx');
 assert.doesNotMatch(server,/list\(data_bytes\)/);
 assert.match(server,/audio_level/);
 assert.match(app,/socket\.on\('audio_level'/);
 assert.doesNotMatch(app,/socket\.on\('audio_data'/);
});
test('audio meter UI updates are throttled, not main-App renders at every animation frame',()=>{
 const app=read('src/App.jsx');
 assert.match(app,/now - lastMeterUpdate >= 100/);
 assert.match(app,/setMicAudioData/);
});
test('Gemini turn completion does not delete queued speaker audio',()=>{
 const spark=read('backend/spark.py');
 const section=spark.slice(spark.indexOf('# Turn/Response Loop Finished'),spark.indexOf('async def play_audio'));
 assert.doesNotMatch(section,/audio_in_queue\.get_nowait\(\)/);
 assert.match(spark,/def clear_audio_queue/); // explicit interruption still supported
});
