// Optional local VoiceStudio playback. The existing Chromium AEC microphone
// remains muted during synthesis AND while any generated audio is audible.
export class VoiceStudioSpeech {
 constructor({render,bridge,AudioCtor=globalThis.Audio,BlobCtor=globalThis.Blob,
  URLApi=globalThis.URL,isUserMuted=()=>false,onComplete=()=>{},onError=()=>{}}){
  this.render=render;
  this.bridge=bridge;
  this.AudioCtor=AudioCtor;
  this.BlobCtor=BlobCtor;
  this.URLApi=URLApi;
  this.isUserMuted=isUserMuted;
  this.onComplete=onComplete;
  this.onError=onError;
  this.active=false;
  this.finish=null;
  this.audio=null;
  this.url=null;
  this.timer=null;
 }
 speak(text){
  if(this.active)this.stop();
  let completed=false;
  const finish=(failed)=>{
   if(completed)return;
   completed=true;
   this.active=false;
   this.finish=null;
   if(this.timer!==null){clearTimeout(this.timer);this.timer=null;}
   try{this.audio?.pause?.();}catch{}
   this.audio=null;
   if(this.url){
    try{this.URLApi?.revokeObjectURL?.(this.url);}catch{}
    this.url=null;
   }
   try{this.bridge?.setMuted?.(this.isUserMuted()||!this.bridge?.ready);}catch{}
   this.onComplete(Boolean(failed));
  };
  if(!this.bridge?.ready||typeof this.render!=='function'||
     typeof text!=='string'||!text.trim()||!this.AudioCtor||
     !this.BlobCtor||!this.URLApi?.createObjectURL){
   finish(true);
   return false;
  }
  const fail=()=>{
   if(completed)return;
   this.onError('VoiceStudio speech is unavailable. Check the local VoiceStudio service and accepted model licence.');
   finish(true);
  };
  try{
   this.bridge.setMuted(true);
   this.active=true;
   this.finish=finish;
   this.timer=setTimeout(fail,115000);
   Promise.resolve().then(()=>this.render(text.trim())).then(packet=>{
    if(completed)return;
    if(packet?.contentType!=='audio/wav'||
       !(packet.bytes instanceof Uint8Array)||packet.bytes.length<12){
     fail();return;
    }
    this.url=this.URLApi.createObjectURL(
     new this.BlobCtor([packet.bytes],{type:'audio/wav'}));
    this.audio=new this.AudioCtor(this.url);
    this.audio.onended=()=>finish(false);
    this.audio.onerror=fail;
    Promise.resolve(this.audio.play()).catch(fail);
   }).catch(fail);
   return true;
  }catch{
   fail();
   return false;
  }
 }
 stop(){
  if(this.active)this.finish?.(true);
 }
}
