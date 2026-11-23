const test=require('node:test');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const getModule=()=>import(pathToFileURL(path.resolve(__dirname,'../src/audio/VoiceStudioSpeech.mjs')).href);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const wave=Uint8Array.from([82,73,70,70,4,0,0,0,87,65,86,69]);
function fixture({render=async()=>({contentType:'audio/wav',bytes:wave}),userMuted=()=>false}={}){
 const actions=[],state={ready:true,muted:false,setMuted(v){this.muted=v;actions.push('mute:'+v)}};
 const urls={createObjectURL(){actions.push('url:create');return 'blob:spark'},revokeObjectURL(u){actions.push('url:revoke:'+u)}};
 class Audio{
  constructor(url){this.src=url;this.paused=false;fixtureAudio=this;actions.push('audio:new')}
  async play(){actions.push('audio:play')}
  pause(){this.paused=true;actions.push('audio:pause')}
  end(){this.onended?.()}
  error(){this.onerror?.()}
 }
 let fixtureAudio,errors=[],completed=[];
 return {bridge:state,actions,urls,AudioCtor:Audio,render,userMuted,
  getAudio:()=>fixtureAudio,errors,completed};
}
test('local voice mutes microphone during synthesis and playback, then restores user mute',async()=>{
 const {VoiceStudioSpeech}=await getModule();
 const f=fixture();
 const speech=new VoiceStudioSpeech({render:f.render,bridge:f.bridge,AudioCtor:f.AudioCtor,
   BlobCtor:Blob,URLApi:f.urls,isUserMuted:f.userMuted,
   onComplete:failed=>f.completed.push(failed),onError:x=>f.errors.push(x)});
 assert.equal(speech.speak('Good evening'),true);
 assert.equal(f.bridge.muted,true);
 await tick();
 assert.ok(f.actions.includes('audio:play'));
 assert.equal(f.bridge.muted,true);
 f.getAudio().end();
 assert.deepEqual(f.completed,[false]);
 assert.equal(f.bridge.muted,false);
 assert.ok(f.actions.includes('url:revoke:blob:spark'));
 speech.stop();
 assert.deepEqual(f.completed,[false]);
});

test('VoiceStudio playback failure is fail-closed, microphone is not re-enabled when user muted',async()=>{
 const {VoiceStudioSpeech}=await getModule();
 const f=fixture({userMuted:()=>true,render:async()=>{throw Error('arbitrary upstream secret')}});
 const speech=new VoiceStudioSpeech({render:f.render,bridge:f.bridge,AudioCtor:f.AudioCtor,
  BlobCtor:Blob,URLApi:f.urls,isUserMuted:f.userMuted,
  onComplete:failed=>f.completed.push(failed),onError:x=>f.errors.push(x)});
 speech.speak('Secret-free failed speech');
 await tick();
 assert.equal(f.bridge.muted,true);
 assert.deepEqual(f.completed,[true]);
 assert.equal(f.errors.length,1);
 assert.doesNotMatch(f.errors[0],/secret|bearer|arbitrary/i);
});

test('cancelled synthesis cannot start late playback or acknowledge twice',async()=>{
 const {VoiceStudioSpeech}=await getModule();
 let release;
 const f=fixture({render:()=>new Promise(resolve=>{release=resolve})});
 const speech=new VoiceStudioSpeech({render:f.render,bridge:f.bridge,AudioCtor:f.AudioCtor,
  BlobCtor:Blob,URLApi:f.urls,isUserMuted:f.userMuted,
  onComplete:failed=>f.completed.push(failed)});
 speech.speak('Hello');
 await tick();
 speech.stop();
 release({contentType:'audio/wav',bytes:wave});
 await tick();
 assert.equal(f.getAudio(),undefined);
 assert.deepEqual(f.completed,[true]);
 assert.equal(f.bridge.muted,false);
});
