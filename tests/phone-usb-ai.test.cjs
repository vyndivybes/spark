const test=require('node:test');
const assert=require('node:assert/strict');
const {createPhoneUsbBridge}=require('../electron/phone-usb-bridge.cjs');
const now=()=>1000,token='a'.repeat(64),code='12004567';
function instance(respond=async ({prompt,history})=>({answer:'I heard '+prompt,provider:'gemini'})){
 return createPhoneUsbBridge({port:0,now,generateCode:()=>code,generateToken:()=>token,mobileChat:respond});
}
async function req(port,path,body,auth){
 return fetch('http://127.0.0.1:'+port+path,{method:'POST',headers:{'Content-Type':'application/json',...(auth?{Authorization:'Bearer '+auth}:{})},body:JSON.stringify(body)});
}
test('mobile AI is opt-in on the desktop and unavailable before explicit owner consent',async()=>{
 const s=instance();const v=await s.start();
 try{
  assert.equal(v.aiEnabled,false);
  const pair=await req(v.port,'/pair',{code});
  assert.equal(pair.status,200);
  const blocked=await req(v.port,'/mobile-chat',{sequence:1,prompt:'What can you do?'},token);
  assert.equal(blocked.status,403);
  assert.equal((await blocked.json()).code,'AI_DISABLED');
  assert.equal(s.setAiEnabled(true).aiEnabled,true);
  const reply=await req(v.port,'/mobile-chat',{sequence:1,prompt:'What can you do?'},token);
  assert.equal(reply.status,200);
  assert.deepEqual(await reply.json(),{ok:true,answer:'I heard What can you do?',provider:'gemini',sequence:1,advisoryOnly:true});
 }finally{await s.stop();}
 assert.equal(s.status().aiEnabled,false);
});

test('only the bearer holder may read replies, and replay/invalid inputs fail closed',async()=>{
 let calls=0;
 const s=instance(async({prompt})=>{calls++;return{answer:'Echo '+prompt,provider:'groq'}});
 const v=await s.start();s.setAiEnabled(true);
 try{
  assert.equal((await req(v.port,'/mobile-chat',{sequence:1,prompt:'Explain lift.'},null)).status,403);
  assert.equal((await req(v.port,'/mobile-chat',{sequence:1,prompt:'Explain lift.'},'f'.repeat(64))).status,403);
  await req(v.port,'/pair',{code});
  for(const [sequence,prompt] of [[0,'Explain lift.'],[1,'x'],[1,'x'.repeat(500)]]){
   assert.equal((await req(v.port,'/mobile-chat',{sequence,prompt},token)).status,422);
  }
  const good=await req(v.port,'/mobile-chat',{sequence:1,prompt:'Explain lift.'},token);
  assert.equal(good.status,200);
  assert.equal((await req(v.port,'/mobile-chat',{sequence:1,prompt:'Explain lift.'},token)).status,409);
  assert.equal(calls,1);
 }finally{await s.stop();}
});

test('conversation history is session bounded, not persisted or exposed to Android via status',async()=>{
 const histories=[];
 const s=instance(async({prompt,history})=>{histories.push(history);return {answer:'Answer',provider:'gemini'};});
 const v=await s.start();s.setAiEnabled(true);await req(v.port,'/pair',{code});
 try{
  const first=await req(v.port,'/mobile-chat',{sequence:1,prompt:'Who are you?'},token);
  assert.equal(first.status,200);
  const second=await req(v.port,'/mobile-chat',{sequence:2,prompt:'And now?'},token);
  assert.equal(second.status,200);
  assert.deepEqual(histories[0],[]);
  assert.deepEqual(histories[1],[{role:'user',content:'Who are you?'},{role:'assistant',content:'Answer'}]);
  assert.equal(s.status().historyCount,undefined);
  assert.equal(s.status().pending,false);
 }finally{await s.stop();}
});

test('provider failure and unsupported tool-shaped output cannot authorize any action',async()=>{
 const s=instance(async()=>{throw Error('secret upstream bearer xxx');});
 const v=await s.start();s.setAiEnabled(true);await req(v.port,'/pair',{code});
 try{
  const r=await req(v.port,'/mobile-chat',{sequence:1,prompt:'Explain aircraft.'},token);
  assert.equal(r.status,503);
  assert.doesNotMatch(await r.text(),/secret upstream/i);
 }finally{await s.stop();}
 const s2=instance(async()=>({answer:'Good',provider:'gemini',execute:true}));
 const v2=await s2.start();s2.setAiEnabled(true);await req(v2.port,'/pair',{code});
 try{
  const r=await req(v2.port,'/mobile-chat',{sequence:1,prompt:'Explain aircraft.'},token);
  assert.equal(r.status,503);
 }finally{await s2.stop();}
});
