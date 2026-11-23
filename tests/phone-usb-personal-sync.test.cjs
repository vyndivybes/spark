const test=require('node:test');
const assert=require('node:assert/strict');
const {createPhoneUsbBridge}=require('../electron/phone-usb-bridge.cjs');
const code='12348765',token='d'.repeat(64);
const sample={notes:['Inspect tyre'],tasks:[{title:'Wash bicycle',done:false}]};
const fetchPost=(port,path,obj,bearer)=>fetch('http://127.0.0.1:'+port+path,{
 method:'POST',headers:{'Content-Type':'application/json',...(bearer?{Authorization:'Bearer '+bearer}:{})},
 body:JSON.stringify(obj)
});
test('personal sync needs separate desktop consent and authenticated physical USB pairing',async()=>{
 let writes=0;
 const s=createPhoneUsbBridge({port:0,generateCode:()=>code,generateToken:()=>token,now:()=>1000,
  mobileSync:async(records)=>{writes++;return records;}});
 const a=await s.start();
 try{
  assert.equal(a.syncEnabled,false);
  assert.equal((await fetchPost(a.port,'/mobile-sync',{sequence:1,records:sample})).status,403);
  assert.equal((await fetchPost(a.port,'/pair',{code})).status,200);
  let blocked=await fetchPost(a.port,'/mobile-sync',{sequence:1,records:sample},token);
  assert.equal(blocked.status,403);
  assert.equal((await blocked.json()).code,'SYNC_DISABLED');
  assert.equal(writes,0);
  assert.equal(s.setSyncEnabled(true).syncEnabled,true);
  assert.equal((await fetchPost(a.port,'/mobile-sync',{sequence:1,records:sample},'f'.repeat(64))).status,403);
  const accepted=await fetchPost(a.port,'/mobile-sync',{sequence:1,records:sample},token);
  assert.equal(accepted.status,200);
  assert.deepEqual(await accepted.json(),{ok:true,personalOnly:true,sequence:1,records:sample});
  assert.equal(writes,1);
  assert.equal((await fetchPost(a.port,'/mobile-sync',{sequence:1,records:sample},token)).status,409);
  assert.equal(writes,1);
  s.setSyncEnabled(false);
  assert.equal((await fetchPost(a.port,'/mobile-sync',{sequence:2,records:sample},token)).status,403);
 }finally{await s.stop();}
 assert.equal(s.status().syncEnabled,false);
});
test('USB rejects invalid personal payloads and never invokes persistence',async()=>{
 let writes=0;
 const s=createPhoneUsbBridge({port:0,generateCode:()=>code,generateToken:()=>token,now:()=>1000,
   mobileSync:async(records)=>{writes++;return records;}});
 const a=await s.start();s.setSyncEnabled(true);await fetchPost(a.port,'/pair',{code});
 try{
  for(const invalid of [
   {notes:[],tasks:[],execute:'shell'},
   {notes:['x'.repeat(241)],tasks:[]},
   {notes:[],tasks:[{title:'',done:false}]},
   {notes:[],tasks:[{title:'hi',done:false,file:'../../secret'}]},
  ]){
   assert.equal((await fetchPost(a.port,'/mobile-sync',{sequence:1,records:invalid},token)).status,422);
  }
  assert.equal(writes,0);
 }finally{await s.stop();}
});
test('personal sync never leaks upstream storage failure or raw data',async()=>{
 const s=createPhoneUsbBridge({port:0,generateCode:()=>code,generateToken:()=>token,now:()=>1000,
   mobileSync:async()=>{throw Error('secret local file path private');}});
 const a=await s.start();s.setSyncEnabled(true);await fetchPost(a.port,'/pair',{code});
 try{
  const r=await fetchPost(a.port,'/mobile-sync',{sequence:1,records:sample},token);
  assert.equal(r.status,503);
  assert.doesNotMatch(await r.text(),/private|secret local/i);
 }finally{await s.stop();}
});
