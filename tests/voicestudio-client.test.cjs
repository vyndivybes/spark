const test=require('node:test');
const assert=require('node:assert/strict');
const {createVoiceStudioClient}=require('../electron/voicestudio-client.cjs');

const wave=Uint8Array.from([82,73,70,70,4,0,0,0,87,65,86,69,1,2,3,4]);
const response=(body=wave,headers={'content-type':'audio/wav'})=>
 new Response(body,{status:200,headers});

test('local VoiceStudio provider defaults disabled and issues no network request',async()=>{
 let calls=0;
 const client=createVoiceStudioClient({enabled:false,fetchImpl:()=>{calls++;throw Error('not called')}});
 await assert.rejects(client.render('SPARK online'),/VOICESTUDIO_DISABLED/);
 assert.equal(calls,0);
});

test('VoiceStudio accepts only numeric local loopback ports',()=>{
 for(const port of ['3900/path','evil.example','65536','80','0','3900@evil','0xF3C0']){
   assert.throws(()=>createVoiceStudioClient({enabled:true,port}),/VOICESTUDIO_PORT_INVALID/);
 }
});

test('VoiceStudio local TTS uses strict outbound host, bounded JSON request and WAV validation',async()=>{
 let called=0;
 const client=createVoiceStudioClient({
  enabled:true,port:'3900',fetchImpl:async(url,options)=>{
   called++;
   assert.equal(url,'http://127.0.0.1:3900/v1/audio/speech');
   assert.equal(options.method,'POST');
   assert.equal(options.redirect,'manual');
   assert.equal(options.headers['Content-Type'],'application/json');
   assert.ok(options.signal);
   assert.deepEqual(JSON.parse(options.body),{
     model:'tts-1',input:'SPARK online',voice:'default',response_format:'wav',speed:1});
   return response();
  }
 });
 const result=await client.render(' SPARK online ');
 assert.equal(called,1);
 assert.equal(result.contentType,'audio/wav');
 assert.deepEqual(Array.from(result.bytes),Array.from(wave));
});

test('invalid text and remote or malformed outputs never reach the cockpit as speech',async()=>{
 const client=createVoiceStudioClient({enabled:true,fetchImpl:async()=>response()});
 for(const text of ['',null,'x'.repeat(1601)]){
   await assert.rejects(client.render(text),/VOICESTUDIO_TEXT_INVALID/);
 }
 for(const bad of [
   new Response(null,{status:302,headers:{location:'https://evil.example'}}),
   new Response('oops',{status:200,headers:{'content-type':'text/html'}}),
   response(Uint8Array.from([1,2,3,4])),
   response(wave,{'content-type':'audio/wav','content-length':'20000000'})
 ]){
   const c=createVoiceStudioClient({enabled:true,fetchImpl:async()=>bad});
   await assert.rejects(c.render('SPARK'),/VOICESTUDIO_(UNAVAILABLE|AUDIO_INVALID|AUDIO_TOO_LARGE)/);
 }
});

test('bounded streaming refuses oversized audio without buffering entire response',async()=>{
 const huge=new Uint8Array(13*1024*1024);
 huge.set(wave);
 const client=createVoiceStudioClient({enabled:true,fetchImpl:async()=>response(huge)});
 await assert.rejects(client.render('SPARK'),/VOICESTUDIO_AUDIO_TOO_LARGE/);
});

test('VoiceStudio does not leak fetch failures to the cockpit',async()=>{
 const client=createVoiceStudioClient({enabled:true,fetchImpl:async()=>{throw Error('secret bearer token 123')}});
 await assert.rejects(client.render('SPARK'),error=>
  error.message==='VOICESTUDIO_UNAVAILABLE');
});
