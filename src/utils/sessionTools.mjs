/* SPARK systems report and explicit session export helpers.
 * Only known health fields are copied. Conversation export is user-initiated.
 */
const labels=[
 ['AI provider','ai_provider'],
 ['Model','live_model'],
 ['Voice profile','live_profile'],
 ['Live connection','live_state'],
 ['Audio transport','audio_transport'],
 ['Hands-free AEC','hands_free_ready'],
 ['Gemini credential configured','gemini_configured'],
 ['Groq credential configured','groq_configured'],
 ['Last connection code','live_error_code'],
 ['Backend uptime (seconds)','uptime_seconds'],
];

export function formatHealthReport(status={}) {
  const p=status && typeof status==='object' ? status : {};
  const val=(k)=>{
    if (['hands_free_ready','gemini_configured','groq_configured'].includes(k)) return p[k] === true?'ready':'not ready';
    if (k==='uptime_seconds') return String(Math.max(0,Math.min(8640000,Number.isFinite(p[k])?Math.floor(p[k]):0)));
    const value=p[k];
    return typeof value==='string' && /^[a-z0-9._/\-]{1,72}$/i.test(value)?value:'unknown';
  };
  const host=p.host&&typeof p.host==='object'?p.host:{};
  const limited=(key,max,suffix,places=1)=>{
    const num=host[key];
    return typeof num==='number'&&Number.isFinite(num)&&num>=0&&num<=max
      ?num.toFixed(places)+suffix:'unavailable';
  };
  return [
    'SPARK systems report — no keys or conversation content',
    ...labels.map(([label,k])=>label+': '+val(k)),
    'CPU: '+limited('cpu_percent',100,'%'),
    'RAM usage: '+limited('ram_percent',100,'%'),
    'Disk available: '+limited('disk_free_gb',1048576,' GB',2),
    'Battery: '+limited('battery_percent',100,'%'),
    'AC power: '+(host.ac_connected===true?'connected':host.ac_connected===false?'disconnected':'unavailable'),
    'Quota counters are not provided by external AI providers.',
  ].join('\n');
}

const safeURL=(url)=>{
 try {
   const parsed=new URL(url);
   if(parsed.protocol!=='https:' || !parsed.hostname || parsed.username || parsed.password) return null;
   return parsed.href.length<=2048 ? parsed.href : null;
 } catch (_) {return null;}
};
const clean=(value,max)=>String(value??'').replace(/\0/g,'').slice(0,max);

export function formatTranscript(messages=[], at=new Date()) {
  const when=(at instanceof Date && !Number.isNaN(at.getTime()))?at.toISOString():new Date().toISOString();
  const output=['# SPARK session transcript','','Exported: '+when,
    'Contains conversation content. Keep this file private.','','---'];
  const records=Array.isArray(messages)?messages.slice(-200):[];
  let used=output.join('\n').length;
  for(const msg of records){
    if(!msg || typeof msg!=='object') continue;
    if(used>190000) break;
    const sender=clean(msg.sender||'Unknown',36).replace(/[\r\n#]/g,' ');
    const time=clean(msg.time||'',36).replace(/[\r\n]/g,' ');
    const body=clean(msg.text||'',4000);
    const lines=['','### '+sender+(time?' — '+time:''),'',body];
    if(Array.isArray(msg.sources)){
      for(const item of msg.sources.slice(0,5)){
        const url=safeURL(item?.url);
        if(url){
          const title=clean(item.title||'Source',100).replace(/[\r\n[\]()]/g,' ');
          lines.push('','Source: '+title+' — '+url);
        }
      }
    }
    used+=lines.join('\n').length;
    output.push(...lines);
  }
  return output.join('\n').slice(0,205000)+'\n';
}
