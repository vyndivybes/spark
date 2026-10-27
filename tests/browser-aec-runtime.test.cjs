const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

const bridgePath=pathToFileURL(path.resolve(__dirname,'../src/audio/BrowserEchoAudio.mjs')).href;

test('startup playback opens the speaker without requesting or sending microphone audio',async()=>{
  const originalNavigator=globalThis.navigator, originalWindow=globalThis.window;
  const mock=mockAudio();
  let requests=0, bridge;
  try {
    Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{
      getUserMedia:async()=>{requests++;throw Error('Microphone must stay closed');}
    }}});
    globalThis.window={AudioContext:mock.AudioContext};
    const {BrowserEchoAudio}=await import(bridgePath);
    bridge=new BrowserEchoAudio({socket:mock.socket});
    await bridge.start({playbackOnly:true});
    assert.equal(bridge.ready,true);
    assert.equal(bridge.muted,true);
    assert.equal(bridge.isCaptureAvailable(),false);
    mock.events.get('browser_audio')(new Uint8Array([0,0,0,0]));
    assert.equal(mock.playback.length,1);
    assert.equal(requests,0);
    assert.equal(mock.emitted.length,0);
    bridge.stop();
    assert.equal(mock.events.has('browser_audio'),false);
  } finally {
    bridge?.stop();
    Object.defineProperty(globalThis,'navigator',{configurable:true,value:originalNavigator});
    globalThis.window=originalWindow;
  }
});

function mockAudio(echoCancellation=true) {
  const events = new Map();
  const emitted = [];
  const tracks = [Object.assign(new EventTarget(), {
    muted:false, readyState:'live',
    getSettings:()=>({echoCancellation}),stop(){this.stopped=true;}
  })];
  const socket={
    connected:true,
    on:(name,fn)=>events.set(name,fn),
    off:(name)=>events.delete(name),
    emit:(name,data)=>emitted.push({name,data})
  };
  const playback=[];
  const analyser={frequencyBinCount:256,fftSize:512,
    getByteFrequencyData(bins){bins.fill(96);},disconnect(){this.disconnected=true;}};
  class AudioContext {
    constructor(){
      this.currentTime=0;this.state='running';this.destination={};this.sampleRate=48000;
      this.audioWorklet={addModule:async()=>{}};
    }
    createMediaStreamSource(){return {connect(){},disconnect(){}};}
    createAnalyser(){return analyser;}
    createBuffer(_channels,count,rate){
      return {duration:count/rate,getChannelData:()=>new Float32Array(count)};
    }
    createBufferSource(){
      return {connect(){},disconnect(){},start(at){playback.push(at);},stop(){}};
    }
    async resume(){this.state='running';}
    async close(){this.state='closed';}
  }
  class AudioWorkletNode {
    constructor(){
      this.port={postMessage(_){},onmessage:null};
      mockAudio.lastWorklet=this;
    }
    connect(){}
    disconnect(){}
  }
  return {socket,tracks,events,emitted,playback,analyser,AudioContext,AudioWorkletNode};
}

test('verified AEC streams multiple speech turns continuously with no manual rearm',async()=>{
  const originalNavigator=globalThis.navigator,originalWindow=globalThis.window;
  const originalWorklet=globalThis.AudioWorkletNode;
  const mock=mockAudio();
  let microphoneRequests=0;
  try {
    Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{
      getUserMedia:async()=>{microphoneRequests++;return {getAudioTracks:()=>mock.tracks,getTracks:()=>mock.tracks};}
    }}});
    globalThis.window={AudioContext:mock.AudioContext,AudioWorkletNode:mock.AudioWorkletNode,
      location:{href:'http://localhost:5173/'}};
    globalThis.AudioWorkletNode=mock.AudioWorkletNode;
    const {BrowserEchoAudio}=await import(bridgePath);
    const bridge=new BrowserEchoAudio({socket:mock.socket});
    await bridge.start();
    assert.equal(bridge.ready,true);
    assert.equal(bridge.readSpectrum().bins[0],96);
    assert.equal(bridge.readSpectrum().sampleRate,48000);
    assert.equal(microphoneRequests,1,'Spectrum must reuse the approved microphone stream');
    const port=mockAudio.lastWorklet.port;
    const chunk=()=>port.onmessage({data:{type:'pcm',pcm:new ArrayBuffer(3200)}});
    chunk(); // user speaks
    const speaker=mock.events.get('browser_audio');
    assert.equal(typeof speaker,'function');
    speaker(new Uint8Array([0,0,0,0])); // model speaks via same audio context
    chunk(); // user's next question: MUST stay enabled hands-free
    assert.equal(mock.emitted.filter(e=>e.name==='browser_mic_pcm').length,2);
    assert.equal(mock.playback.length,1);
    bridge.setMuted(true);chunk();
    assert.equal(bridge.readSpectrum(),null,'Muted input must not feed voice pulses');
    assert.equal(mock.emitted.filter(e=>e.name==='browser_mic_pcm').length,2);
    bridge.stop();
    assert.equal(mock.tracks[0].stopped,true);
    assert.equal(mock.events.has('browser_audio'),false);
    assert.equal(mock.analyser.disconnected,true);
  }finally{
    Object.defineProperty(globalThis,'navigator',{configurable:true,value:originalNavigator});
    globalThis.window=originalWindow;
    globalThis.AudioWorkletNode=originalWorklet;
  }
});

test('AEC unsupported means capture fails closed instead of falling back to raw microphone',async()=>{
  const originalNavigator=globalThis.navigator,originalWindow=globalThis.window;
  const originalWorklet=globalThis.AudioWorkletNode;
  const mock=mockAudio(false);
  try{
    Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{
      getUserMedia:async()=>({getAudioTracks:()=>mock.tracks,getTracks:()=>mock.tracks})
    }}});
    globalThis.window={AudioContext:mock.AudioContext,AudioWorkletNode:mock.AudioWorkletNode,
      location:{href:'http://localhost:5173/'}};
    globalThis.AudioWorkletNode=mock.AudioWorkletNode;
    const {BrowserEchoAudio}=await import(bridgePath);
    const bridge=new BrowserEchoAudio({socket:mock.socket});
    await assert.rejects(()=>bridge.start(),/echo cancellation is not active/i);
    assert.equal(mock.tracks[0].stopped,true);
    assert.equal(mock.emitted.some(e=>e.name==='browser_mic_pcm'),false);
  }finally{
    Object.defineProperty(globalThis,'navigator',{configurable:true,value:originalNavigator});
    globalThis.window=originalWindow;
    globalThis.AudioWorkletNode=originalWorklet;
  }
});

test('Windows mute and device loss suppress capture, report recovery, and respect user mute', async () => {
  const originalNavigator=globalThis.navigator, originalWindow=globalThis.window;
  const originalWorklet=globalThis.AudioWorkletNode;
  const mock=mockAudio();
  const states=[];
  let bridge;
  try {
    Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{
      getUserMedia:async()=>({getAudioTracks:()=>mock.tracks,getTracks:()=>mock.tracks})
    }}});
    globalThis.window={AudioContext:mock.AudioContext,AudioWorkletNode:mock.AudioWorkletNode,
      location:{href:'http://localhost:5173/'}};
    globalThis.AudioWorkletNode=mock.AudioWorkletNode;
    const {BrowserEchoAudio}=await import(bridgePath);
    bridge=new BrowserEchoAudio({socket:mock.socket,onCaptureState:state=>states.push(state)});
    mock.tracks[0].muted=true;
    await bridge.start();
    const chunk=()=>mockAudio.lastWorklet.port.onmessage({data:{type:'pcm',pcm:new ArrayBuffer(3200)}});
    assert.equal(bridge.isCaptureAvailable(),false,'A running context cannot prove the device is unmuted');
    chunk();
    assert.equal(mock.emitted.length,0);
    assert.equal(bridge.readSpectrum(),null);
    mock.tracks[0].muted=false;
    mock.tracks[0].dispatchEvent(new Event('unmute'));
    chunk();
    assert.equal(mock.emitted.length,1);
    mock.tracks[0].muted=true;
    mock.tracks[0].dispatchEvent(new Event('mute'));
    chunk();
    assert.equal(mock.emitted.length,1);
    bridge.setMuted(true);
    mock.tracks[0].muted=false;
    mock.tracks[0].dispatchEvent(new Event('unmute'));
    chunk();
    assert.equal(mock.emitted.length,1,'Device recovery must preserve explicit user mute');
    bridge.setMuted(false);
    mock.tracks[0].readyState='ended';
    mock.tracks[0].dispatchEvent(new Event('ended'));
    chunk();
    assert.equal(mock.emitted.length,1);
    assert.deepEqual(states,[{available:true},{available:false},{available:true},{available:false}]);
    bridge.stop();
    mock.tracks[0].dispatchEvent(new Event('mute'));
    assert.equal(states.length,4,'Stopped capture must remove device listeners');
  } finally {
    bridge?.stop();
    Object.defineProperty(globalThis,'navigator',{configurable:true,value:originalNavigator});
    globalThis.window=originalWindow;
    globalThis.AudioWorkletNode=originalWorklet;
  }
});
