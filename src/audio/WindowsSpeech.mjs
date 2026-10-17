/* Quota-free Windows/Chromium speech for SPARK Groq voice.
 * Web Speech TTS does not run through the WebAudio context. Therefore mic
 * PCM is CLOSED until speech ends and the browser has finished speaking.
 * This prevents speaker→mic feedback without changing Gemini Charon path.
 */
export function chooseEnglishVoice(voices) {
  if (!Array.isArray(voices)) return null;
  const uk=voices.filter(v=>/^en[-_]GB$/i.test(v?.lang||''));
  return uk.find(v=>/george|ryan|daniel|david|oliver|mark|male/i.test(v.name||'')) ||
    uk[0] || voices.find(v=>/^en([-_]|$)/i.test(v?.lang||'')) || voices[0] || null;
}
export class WindowsSpeech {
  constructor({synth,Utterance,bridge,isUserMuted=()=>false,onComplete=()=>{},onError=()=>{}}) {
    this.synth=synth;
    this.Utterance=Utterance;
    this.bridge=bridge;
    this.isUserMuted=isUserMuted;
    this.onComplete=onComplete;
    this.onError=onError;
    this.active=false;
    this.timer=null;
    this.finish=null;
  }
  speak(text) {
    if (this.active) this.stop();
    let completed=false;
    const finish=(failed)=>{
      if (completed) return;
      completed=true;
      this.active=false;
      this.finish=null;
      if (this.timer!==null){clearTimeout(this.timer);this.timer=null;}
      // Existing user-mute policy is authoritative: never turn on a muted mic.
      try {this.bridge?.setMuted?.(this.isUserMuted() || !this.bridge?.ready);}catch(_){}
      this.onComplete(Boolean(failed));
    };
    if (!this.synth?.speak || !this.Utterance || !this.bridge?.ready ||
        typeof text!=='string' || !text.trim()) {
      finish(true);
      return false;
    }
    try {
      const utterance=new this.Utterance(text.trim().slice(0,1600));
      utterance.lang='en-GB';
      utterance.rate=0.96;
      utterance.pitch=0.91;
      utterance.volume=1;
      const preferred=chooseEnglishVoice(this.synth.getVoices?.()||[]);
      if (preferred) utterance.voice=preferred;
      utterance.onend=()=>finish(false);
      utterance.onerror=()=>{this.onError('Windows text-to-speech could not play. Check the default speaker and installed English voices.');finish(true);};
      this.bridge.setMuted(true);
      this.active=true;
      this.finish=finish;
      this.synth.cancel?.();
      this.synth.speak(utterance);
      // A missing onend event must not leave the microphone permanently muted.
      this.timer=setTimeout(()=>{this.synth.cancel?.();finish(true);},30000);
      return true;
    } catch(_) {
      this.onError('Windows speech synthesis is unavailable. Verify system speaker and English speech voice.');
      finish(true);
      return false;
    }
  }
  stop() {
    if(this.active){
      try{this.synth?.cancel?.();}catch(_){}
      this.finish?.(true);
    }
  }
}
