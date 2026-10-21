const test=require('node:test');
const assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const {createJarvisBridge,jarvisOrigin,validateQuestion,normalizeReply}=require('../electron/jarvis-bridge.cjs');

test('business bridge authenticates and accepts only fixed portal reads',async()=>{
  const calls=[];
  const bridge=createJarvisBridge({session:{fromPartition:()=>({})},token:'c'.repeat(64),
    businessRead:async portal=>{calls.push(portal);return {ok:true,readOnly:true};}});
  try{
    const base=await bridge.listen();
    const request=body=>fetch(base+'/business-read',{method:'POST',headers:{Authorization:'Bearer '+'c'.repeat(64)},body:JSON.stringify(body)});
    assert.equal((await fetch(base+'/business-read',{method:'POST',body:'{}'})).status,403);
    assert.equal((await request({portal:'https://example.com'})).status,400);
    assert.equal((await request({portal:'vedm',url:'https://example.com'})).status,400);
    assert.equal((await request({portal:'vedm'})).status,200);
    assert.deepEqual(calls,['vedm']);
  }finally{bridge.close();}
});

test('VAOS origin/question validation rejects credentials, redirects and oversized inputs',()=>{
  assert.equal(jarvisOrigin(),'https://vaos.vayushastr.workers.dev');
  for(const value of ['http://example.com','https://user:password@example.com','https://example.com/path','https://example.com/?q=1'])assert.throws(()=>jarvisOrigin(value));
  for(const value of ['abc','a'.repeat(301),'hello\nworld',null])assert.throws(()=>validateQuestion(value));
  assert.equal(validateQuestion('  workforce status  '),'workforce status');
  assert.throws(()=>normalizeReply({data:{answer:'executed',readOnly:false,advisoryOnly:false}}));
  assert.throws(()=>normalizeReply({data:{answer:'executed',readOnly:true,advisoryOnly:true,actionAuthorized:true}}));
});

test('isolated VAOS session serves authenticated advisory requests and can disconnect',async()=>{
  const calls=[];let signedIn=false,options;
  const portal={cookies:{get:async()=>signedIn?[{name:'vaos_session',value:'private-cookie-never-exported'}]:[]},
    clearStorageData:async()=>{signedIn=false;},
    fetch:async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify({data:{answer:'No qualified source evidence.',status:'HOLD',sourceSystem:'VAOS_ADAPTIVE',readOnly:true,advisoryOnly:true,actionAuthorized:false}}));}};
  class Window extends EventEmitter{
    constructor(opts){super();options=opts;this.webContents=new EventEmitter();this.webContents.setWindowOpenHandler=()=>{};}
    async loadURL(url){assert.equal(url,'https://vaos.vayushastr.workers.dev');}
    isDestroyed(){return false;}close(){this.emit('closed');}show(){}focus(){}
  }
  const bridge=createJarvisBridge({BrowserWindow:Window,session:{fromPartition:name=>{assert.equal(name,'persist:spark-vaos-jarvis');return portal;}},token:'a'.repeat(64)});
  try{
    assert.equal((await bridge.ask('What is workforce status?')).code,'SIGN_IN_REQUIRED');
    assert.equal(calls.length,0);
    await bridge.open();
    assert.equal(options.webPreferences.nodeIntegration,false);
    assert.equal(options.webPreferences.sandbox,true);
    signedIn=true;
    const base=await bridge.listen();
    assert.equal((await fetch(base+'/ask',{method:'POST',body:'{}'})).status,403);
    const response=await fetch(base+'/ask',{method:'POST',headers:{Authorization:'Bearer '+'a'.repeat(64)},body:JSON.stringify({question:'What is workforce status?'})});
    const result=await response.json();
    assert.equal(result.ok,true);assert.equal(result.status,'HOLD');
    assert.equal(new URL(calls[0].url).pathname,'/api/adaptive-intelligence');
    assert.equal(new URL(calls[0].url).searchParams.get('q'),'What is workforce status?');
    assert.equal(calls[0].init.method,'GET');assert.equal(calls[0].init.credentials,'include');
    assert.equal(calls[0].init.redirect,'error');
    assert.ok(!JSON.stringify(result).includes('private-cookie'));
    await bridge.disconnect();assert.equal((await bridge.status()).sessionPresent,false);
  }finally{bridge.close();}
});

test('VAOS auth errors return useful states without exposing raw responses',async()=>{
  const bridge=createJarvisBridge({BrowserWindow:null,session:{fromPartition:()=>({cookies:{get:async()=>[{name:'vaos_session'}]},fetch:async()=>new Response('private-error',{status:401})})},token:'b'.repeat(64)});
  const result=await bridge.ask('What is the business status?');
  assert.equal(result.code,'VAOS_HTTP_401');assert.match(result.message,/sign in/);assert.ok(!JSON.stringify(result).includes('private-error'));
});
