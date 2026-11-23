const test=require('node:test');
const assert=require('node:assert/strict');
const {createPhoneUsbBridge}=require('../electron/phone-usb-bridge.cjs');

const summary='Last 7 days\n\nActivities: 3\nSteps: 12,345\nDistance: 56.78 km\n\nSource apps: com.garmin.android.apps.connectmobile\n\nHealth Connect totals may include non-Garmin sources.';
const code='64271938',token='e'.repeat(64);
function bridge(now=()=>1_000_000){
 return createPhoneUsbBridge({port:0,now,generateCode:()=>code,generateToken:()=>token});
}
async function post(port,path,value,{bearer,host,origin,method='POST'}={}){
 return fetch('http://127.0.0.1:'+port+path,{
  method,redirect:'manual',
  headers:{'content-type':'application/json',...(bearer?{authorization:'Bearer '+bearer}:{}),...(host?{host}:{}),...(origin?{origin}:{})},
  body:JSON.stringify(value)
 });
}
test('USB server is opt-in, loopback bound, and its code is not disclosed to the phone',async()=>{
 const b=bridge();
 assert.equal(b.status().listening,false);
 assert.equal(b.take(),null);
 const state=await b.start();
 assert.equal(state.listening,true);
 assert.equal(state.host,'127.0.0.1');
 assert.equal(state.code,code);
 assert.equal(state.paired,false);
 assert.equal(state.expiresAt,1120000);
 const notFound=await fetch('http://127.0.0.1:'+state.port+'/');
 assert.equal(notFound.status,405);
 assert.doesNotMatch(await notFound.text(),new RegExp(code));
 await b.stop();
 assert.equal(b.status().listening,false);
});

test('one-time pairing + bearer + monotonic message sequence gate explicit summary push',async()=>{
 const b=bridge();const {port}=await b.start();
 try {
  assert.equal((await post(port,'/summary',{sequence:1,summary})).status,403);
  assert.equal((await post(port,'/pair',{code:'11111111'})).status,403);
  let r=await post(port,'/pair',{code});
  assert.equal(r.status,200);
  const out=await r.json();
  assert.equal(out.sessionToken,token);
  assert.equal(out.expiresInSeconds,600);
  assert.equal((await post(port,'/pair',{code})).status,409);
  assert.equal((await post(port,'/summary',{sequence:1,summary},{bearer:'f'.repeat(64)})).status,403);
  assert.equal((await post(port,'/summary',{sequence:0,summary},{bearer:token})).status,422);
  r=await post(port,'/summary',{sequence:1,summary},{bearer:token});
  assert.equal(r.status,200);
  assert.equal(b.status().pending,true);
  assert.equal(b.take(),summary);
  assert.equal(b.take(),null);
  assert.equal((await post(port,'/summary',{sequence:1,summary},{bearer:token})).status,409);
  assert.equal((await post(port,'/summary',{sequence:2,summary},{bearer:token})).status,200);
  assert.equal(b.take(),summary);
 } finally{await b.stop();}
});

test('invalid payloads, nonlocal origins, expired sessions and attempts fail closed',async()=>{
 let time=1000;const b=bridge(()=>time);
 const {port}=await b.start();
 try {
  assert.equal((await post(port,'/pair',{code},{origin:'https://evil.example'})).status,403);
  for(let i=0;i<5;i++) {
   const response=await post(port,'/pair',{code:'00000000'});
   assert.equal(response.status,i===4?429:403);
  }
  assert.equal((await post(port,'/pair',{code})).status,429);
 }finally{await b.stop();}
 const another=bridge(()=>time);const state=await another.start();
 try{
  time=state.expiresAt+1;
  assert.equal((await post(state.port,'/pair',{code})).status,410);
 }finally{await another.stop();}
 const sessionBridge=bridge(()=>time);const s=await sessionBridge.start();
 try{
  assert.equal((await post(s.port,'/pair',{code})).status,200);
  time+=600001;
  assert.equal((await post(s.port,'/summary',{sequence:1,summary},{bearer:token})).status,410);
 }finally{await sessionBridge.stop();}
});

test('rejects arbitrary text and does not expose data after stop/restart',async()=>{
 const b=bridge();const {port}=await b.start();
 try{
  assert.equal((await post(port,'/pair',{code})).status,200);
  for(const bad of [
   {sequence:1,summary:'issue purchase order'},
   {sequence:1,summary:summary+'\nsecret'},
   {sequence:1,summary:'x'.repeat(7000)},
   {sequence:1,summary},
  ].slice(0,3)){
   const r=await post(port,'/summary',bad,{bearer:token});
   assert.ok([413,422].includes(r.status),'unexpected '+r.status);
  }
  assert.equal(b.status().pending,false);
 }finally{await b.stop();}
 assert.equal(b.status().paired,false);
 assert.equal(b.take(),null);
});
