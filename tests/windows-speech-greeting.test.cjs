const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');

async function getSpeech() {
 return await import(pathToFileURL(path.resolve(__dirname,'../src/audio/WindowsSpeech.mjs')).href);
}
test('Windows speech uses UK English and locks AEC mic until actual utterance ends',async()=>{
 const {WindowsSpeech}=await getSpeech();
 const events=[]; const bridge={ready:true,muted:false,setMuted(v){this.muted=v;events.push('mute:'+v)}};
 class Utterance {constructor(text){this.text=text;}}
 const synth={speaking:false, cancel(){}, getVoices(){return [
  {lang:'en-US',name:'US Voice'},{lang:'en-GB',name:'Microsoft George Male'}]},
  speak(utterance){this.speaking=true;this.last=utterance;}
 };
 let done=[];
 const speech=new WindowsSpeech({synth,Utterance,bridge,
   isUserMuted:()=>false,onComplete:fail=>done.push(fail)});
 assert.equal(speech.speak('Good morning, sir. SPARK online.'),true);
 assert.equal(bridge.muted,true);
 assert.equal(synth.last.voice.name,'Microsoft George Male');
 assert.ok(synth.last.rate>0.7&&synth.last.rate<1.1);
 synth.last.onend();
 assert.deepEqual(done,[false]);
 assert.equal(bridge.muted,false);
 assert.deepEqual(events,['mute:true','mute:false']);
 speech.stop();
});

test('voice engine failure sends a single failure and does not leave mic muted',async()=>{
 const {WindowsSpeech}=await getSpeech();
 const bridge={ready:true,muted:false,setMuted(v){this.muted=v}};
 const completed=[];
 const speech=new WindowsSpeech({synth:{getVoices(){return []},cancel(){},speak(){throw Error('voice offline')}},
   Utterance:class {constructor(text){this.text=text}},bridge,
   isUserMuted:()=>false,onComplete:fail=>completed.push(fail)});
 assert.equal(speech.speak('Hello'),false);
 assert.equal(bridge.muted,false);
 assert.deepEqual(completed,[true]);
 speech.stop();
});
test('manual mute stays engaged after local Windows speech ends',async()=>{
 const {WindowsSpeech}=await getSpeech();
 let userMuted=true;
 const bridge={ready:true,muted:false,setMuted(v){this.muted=v}};
 let u;
 const speech=new WindowsSpeech({synth:{getVoices(){return []},cancel(){},speak(v){u=v}},
  Utterance:class{},bridge,isUserMuted:()=>userMuted,onComplete:()=>{}});
 speech.speak('SPARK');
 u.onend();
 assert.equal(bridge.muted,true);
 speech.stop();
});
test('provider TTS socket is routed only to the receiving owner and acknowledges completion',()=>{
 const fs=require('node:fs');
 const server=fs.readFileSync(path.resolve(__dirname,'../backend/server.py'),'utf8');
 const app=fs.readFileSync(path.resolve(__dirname,'../src/App.jsx'),'utf8');
 assert.match(server,/sio\.emit\('browser_tts', payload, room=sid\)/);
 assert.match(server,/async def browser_speech_done\(sid, data=None\):/);
 assert.match(server,/audio_loop\.owner_sid != sid/);
 assert.match(app,/socket\.on\('browser_tts'/);
 assert.match(app,/socket\.emit\('browser_speech_done'/);
 assert.match(app,/socket\.off\('browser_tts'/);
});
