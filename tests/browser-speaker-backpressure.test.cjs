const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const moduleUrl=pathToFileURL(path.resolve(__dirname,'../src/audio/BrowserEchoAudio.mjs')).href;

function harness() {
  const errors=[], warnings=[], started=[];
  const ctx={
    currentTime:0,
    destination:{},
    createBuffer(channels,samples,rate){
      assert.equal(channels,1); assert.equal(rate,24000);
      return {duration:samples/rate,getChannelData:()=>new Float32Array(samples)};
    },
    createBufferSource(){
      return {connect(){},disconnect(){},stop(){},
        start(at){started.push(at);}};
    }
  };
  return {ctx,errors,warnings,started};
}

test('more than six seconds of fast Gemini PCM never kills AEC or discards speech',async()=>{
  const {BrowserEchoAudio}=await import(moduleUrl);
  const h=harness();
  const bridge=new BrowserEchoAudio({socket:{off(){}},onError:e=>h.errors.push(e),onWarning:e=>h.warnings.push(e)});
  bridge.audioContext=h.ctx; bridge.ready=true;
  const oneSecond=new Uint8Array(48000);
  for(let i=0;i<24;i++) bridge.playPcm(oneSecond);
  assert.equal(h.errors.length,0);
  assert.equal(h.warnings.length,0);
  assert.equal(bridge.closed,false);
  assert.equal(bridge.ready,true);
  assert.ok(bridge.pendingPcm.length>10,'must queue, not drop, early arriving model PCM');
  assert.ok(bridge.playUntil-h.ctx.currentTime<4,'schedule only a short look-ahead');
  // AudioContext playback clock advances as the browser emits existing speech.
  for(let t=1;t<=28;t++){
    h.ctx.currentTime=t;
    bridge.pumpAudio();
  }
  assert.equal(bridge.pendingPcm.length,0,'full 24 second speech response must drain');
  assert.equal(h.started.length,24,'each PCM chunk is rendered without truncation');
  bridge.stop();
});

test('genuine runaway backlog warns once but does not misreport AEC hardware failure',async()=>{
  const {BrowserEchoAudio}=await import(moduleUrl);
  const h=harness();
  const bridge=new BrowserEchoAudio({socket:{off(){}},onError:e=>h.errors.push(e),onWarning:e=>h.warnings.push(e)});
  bridge.audioContext=h.ctx;bridge.ready=true;
  for(let i=0;i<150;i++) bridge.playPcm(new Uint8Array(48000));
  assert.equal(h.errors.length,0);
  assert.equal(h.warnings.length,1);
  assert.equal(bridge.closed,false);
  assert.equal(bridge.ready,true);
  assert.ok(bridge.pendingPcm.length<=120);
  bridge.stop();
});

test('actual Chromium speaker failure remains fatal and reports once',async()=>{
  const {BrowserEchoAudio}=await import(moduleUrl);
  const h=harness();
  h.ctx.createBuffer=()=>{throw new Error('Windows audio engine failure');};
  const bridge=new BrowserEchoAudio({socket:{off(){}},onError:e=>h.errors.push(e),onWarning:e=>h.warnings.push(e)});
  bridge.audioContext=h.ctx;bridge.ready=true;
  bridge.onSpeaker(new Uint8Array(48000));
  bridge.onSpeaker(new Uint8Array(48000));
  assert.equal(h.errors.length,1);
  assert.equal(h.warnings.length,0);
  assert.equal(bridge.ready,false);
  assert.equal(bridge.closed,true);
});
