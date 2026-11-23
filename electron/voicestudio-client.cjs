'use strict';

// Independent local HTTP adapter. No VoiceStudio source is copied or linked
// into SPARK; the AGPL application and its models are installed separately.
const MAX_AUDIO=12*1024*1024;
const MAX_TEXT=1600;
function choosePort(value){
 if(value==null||value==='')return 3900;
 if(typeof value!=='string'||!/^[0-9]{4,5}$/.test(value))throw Error('VOICESTUDIO_PORT_INVALID');
 const n=Number(value);
 if(n<1024||n>65535)throw Error('VOICESTUDIO_PORT_INVALID');
 return n;
}
function isWave(bytes){
 return bytes.length>=12
  &&bytes[0]===82&&bytes[1]===73&&bytes[2]===70&&bytes[3]===70
  &&bytes[8]===87&&bytes[9]===65&&bytes[10]===86&&bytes[11]===69;
}
function createVoiceStudioClient({
 enabled=process.env.SPARK_VOICE_PROVIDER==='voicestudio',
 port=process.env.SPARK_VOICESTUDIO_PORT,
 fetchImpl=globalThis.fetch
}={}){
 const origin='http://127.0.0.1:'+choosePort(port);
 return Object.freeze({
  async render(text){
   if(!enabled)throw Error('VOICESTUDIO_DISABLED');
   if(typeof text!=='string'||!text.trim()||text.trim().length>MAX_TEXT)
    throw Error('VOICESTUDIO_TEXT_INVALID');
   if(typeof fetchImpl!=='function')throw Error('VOICESTUDIO_UNAVAILABLE');
   const controller=new AbortController();
   const timer=setTimeout(()=>controller.abort(),100000);
   try{
    const r=await fetchImpl(origin+'/v1/audio/speech',{
     method:'POST',redirect:'manual',signal:controller.signal,
     headers:{'Content-Type':'application/json',Accept:'audio/wav'},
     body:JSON.stringify({
      model:'tts-1',input:text.trim(),voice:'default',response_format:'wav',speed:1
     })
    });
    if(!r||r.status!==200)throw Error('VOICESTUDIO_UNAVAILABLE');
    if(!/^audio\/(?:wav|x-wav|wave)(?:\s*;|$)/i.test(r.headers.get('content-type')||''))
     throw Error('VOICESTUDIO_AUDIO_INVALID');
    const size=r.headers.get('content-length');
    if(size!==null && (!/^\d+$/.test(size)||Number(size)>MAX_AUDIO))
     throw Error('VOICESTUDIO_AUDIO_TOO_LARGE');
    if(!r.body||typeof r.body.getReader!=='function')
     throw Error('VOICESTUDIO_AUDIO_INVALID');
    const chunks=[];
    let total=0;
    const reader=r.body.getReader();
    while(true){
     const {done,value}=await reader.read();
     if(done)break;
     if(!(value instanceof Uint8Array))throw Error('VOICESTUDIO_AUDIO_INVALID');
     total+=value.byteLength;
     if(total>MAX_AUDIO){
      await reader.cancel().catch(()=>{});
      throw Error('VOICESTUDIO_AUDIO_TOO_LARGE');
     }
     chunks.push(value);
    }
    const bytes=new Uint8Array(total);
    let offset=0;
    for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
    if(!isWave(bytes))throw Error('VOICESTUDIO_AUDIO_INVALID');
    return {contentType:'audio/wav',bytes};
   }catch(e){
    if(/^VOICESTUDIO_(?:DISABLED|TEXT_INVALID|AUDIO_INVALID|AUDIO_TOO_LARGE)$/.test(e?.message||''))
     throw e;
    // Do not forward upstream response bodies, file paths, API tokens, or headers.
    throw Error('VOICESTUDIO_UNAVAILABLE');
   }finally{clearTimeout(timer);}
  }
 });
}
module.exports={createVoiceStudioClient,choosePort};
