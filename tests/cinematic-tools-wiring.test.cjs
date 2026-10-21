const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const read = p => fs.readFileSync(path.resolve(__dirname,'..',p), 'utf8');

test('opt-in tool calls are authorized by active Live profile before execution',()=>{
 const spark=read('backend/spark.py');
 assert.match(spark, /if not allowed_live_tool\(live_profile\(\), fc\.name\):/);
 assert.match(spark, /if fc\.name == "get_system_status":/);
 assert.match(spark, /response=\{"result": get_system_status\(\)\}/);
 assert.match(spark, /tool_confirmation_required\(fc\.name, self\.permissions\)/);
 assert.match(spark, /asyncio\.wait_for\(future, timeout=45\)/);
 assert.match(spark, /except asyncio\.TimeoutError:/);
 assert.match(spark, /launch_allowed_app, fc\.args\.get\("app", ""\)/);
});
test('only the session-owning window can approve an application launch',()=>{
 const server=read('backend/server.py');
 assert.match(server, /sio\.emit\('tool_confirmation_request', data, room=sid\)/);
 assert.match(server, /getattr\(audio_loop, "owner_sid", None\) != sid/);
 assert.match(server, /audio_loop\.owner_sid = sid/);
});
test('cinematic hands-free default and existing acoustic AEC remain intact',()=>{
 const launcher=read('start-spark.ps1');
 const profile=read('backend/spark_live_profile.py');
 assert.match(launcher, /\[string\]\$LiveProfile = 'cinematic'/);
 assert.match(launcher, /\[string\]\$AudioTransport = 'browser_aec'/);
 assert.match(profile, /if profile == "cinematic_tools":/);
 assert.match(profile, /output = select_live_config\("cinematic", full_config\)/);
});
