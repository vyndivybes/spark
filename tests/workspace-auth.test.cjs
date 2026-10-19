const test=require('node:test');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const {trustedWorkspaceSender}=require('../electron/workspace-auth.cjs');
test('workspace nonce is available only to the trusted root frame',()=>{
 const entry=path.resolve(__dirname,'../dist/index.html');
 const frame={url:pathToFileURL(entry).href};
 const contents={mainFrame:frame};const window={webContents:contents};
 const event={sender:contents,senderFrame:frame};
 assert.equal(trustedWorkspaceSender(event,window,entry,false),true);
 assert.equal(trustedWorkspaceSender({...event,senderFrame:{url:frame.url}},window,entry,false),false);
 assert.equal(trustedWorkspaceSender({...event,sender:{}},window,entry,false),false);
 frame.url='https://example.com';assert.equal(trustedWorkspaceSender(event,window,entry,true),false);
 frame.url='http://localhost:5173/';assert.equal(trustedWorkspaceSender(event,window,entry,true),true);
 assert.equal(trustedWorkspaceSender(event,window,entry,false),false);
});
