const test=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..');
const source=file=>readFileSync(path.join(root,file),'utf8');

test('SPARK exposes Jarvis only through existing owner-gated local session',()=>{
 const server=source('backend/server.py');
 assert.match(server,/@sio.event\s+async def jarvis_ask\(sid, data\)/);
 const segment=server.split('async def jarvis_ask(sid, data):')[1].split('@sio.event')[0];
 assert.match(segment,/workspace_client_allowed/);
 assert.match(segment,/owner_sid/);
 assert.match(segment,/face_auth_enabled/);
 assert.match(segment,/JarvisBridge.from_environment/);
 assert.match(segment,/asyncio.to_thread/);
 assert.doesNotMatch(segment,/subprocess|shell=True/);
});
test('Jarvis interface is a distinct non-authorizing SPARK panel',()=>{
 const app=source('src/App.jsx');
 const panel=source('src/components/JarvisPanel.jsx');
 assert.match(app,/import JarvisPanel/);
 assert.match(app,/showJarvis/);
 assert.match(app,/<JarvisPanel/);
 assert.match(panel,/socket.emit\('jarvis_ask'/);
 assert.match(panel,/socket.workspaceToken/);
 assert.match(panel,/Business actions cannot be authorized here/);
 assert.doesNotMatch(panel,/dangerouslySetInnerHTML|eval\(/);
});
