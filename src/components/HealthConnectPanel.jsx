import React, {useState, useEffect} from 'react';
import {Activity, X, Smartphone, Watch, ClipboardPaste, ShieldCheck} from 'lucide-react';
import {parseHealthConnectSummary} from '../utils/healthConnectSummary.mjs';

/* Activity import remains user-selected and in panel memory. Optional USB
 * companion transfer is polled only while this panel is open, never cloud
 * uploaded or written to the company's systems.
 */
function phoneUsbIpc() {
  try {return window.require?.('electron')?.ipcRenderer || null;} catch {return null;}
}
export default function HealthConnectPanel({onClose}) {
  const [raw,setRaw]=useState('');
  const [summary,setSummary]=useState(null);
  const [error,setError]=useState('');
  const [usb,setUsb]=useState({listening:false,paired:false,pending:false,code:null});
  const [usbNotice,setUsbNotice]=useState('');
  useEffect(()=>{
    let active=true,working=false;
    const poll=async()=>{
      if(!active||working)return;
      working=true;
      try{
        const ipc=phoneUsbIpc();
        if(!ipc)return;
        const next=await ipc.invoke('spark:phone-usb',{action:'status'});
        if(!active)return;
        setUsb(next);
        if(next.pending){
          const imported=await ipc.invoke('spark:phone-usb',{action:'take'});
          if(!active)return;
          if(typeof imported==='string'){
            try{
              setSummary(parseHealthConnectSummary(imported));
              setRaw('');
              setError('');
              setUsbNotice('One Health Connect summary received from the paired Android device.');
            }catch{
              setError('USB summary was not recognized. Copy the summary manually from the companion.');
            }
          }
        }
      }catch{
        if(active)setUsbNotice('USB bridge unavailable in this SPARK session.');
      }finally{working=false;}
    };
    const interval=setInterval(poll,1200);
    void poll();
    return ()=>{
      active=false;
      clearInterval(interval);
      const ipc=phoneUsbIpc();
      // Closing the panel revokes both the short code and paired session.
      if(ipc)void ipc.invoke('spark:phone-usb',{action:'stop'}).catch(()=>{});
    };
  },[]);
  const toggleMobileAi=async()=>{
    const ipc=phoneUsbIpc();
    if(!ipc)return setUsbNotice('SPARK desktop connection unavailable.');
    try{
      const next=await ipc.invoke('spark:phone-usb',{action:'set-ai',enabled:!usb.aiEnabled});
      setUsb(next);
      setUsbNotice(next.aiEnabled
        ? 'Read-only mobile AI enabled for this USB session. Questions will go to the configured desktop provider.'
        : 'Mobile AI disabled. Any further phone prompts are denied.');
    }catch{setUsbNotice('Could not change mobile AI permission. Restart USB pairing.');}
  };
  const togglePersonalSync=async()=>{
    const ipc=phoneUsbIpc();
    if(!ipc)return setUsbNotice('SPARK desktop connection unavailable.');
    try{
      const next=await ipc.invoke('spark:phone-usb',{action:'set-sync',enabled:!usb.syncEnabled});
      setUsb(next);
      setUsbNotice(next.syncEnabled
        ? 'Personal notes/tasks sync enabled for this USB session. Android must still tap Sync explicitly.'
        : 'Personal notes/tasks sync disabled. Saved PC records remain in your local SPARK data folder.');
    }catch{setUsbNotice('Could not change personal sync permission. Reopen USB pairing.');}
  };
  const changeUsb=async(action)=>{
    const ipc=phoneUsbIpc();
    if(!ipc){setUsbNotice('USB pairing requires the installed SPARK Electron desktop app.');return;}
    try{
      const result=await ipc.invoke('spark:phone-usb',{action});
      setUsb(action==='stop'?{listening:false,paired:false,pending:false,code:null}:result);
      setUsbNotice(action==='start'?'USB bridge started locally. Run adb reverse, then enter this code on Android.':'USB session revoked. No health data is retained.');
    }catch{
      setUsbNotice('USB bridge could not start. Check whether port 38177 is already in use.');
    }
  };
  const load=()=>{
    try{
      setSummary(parseHealthConnectSummary(raw));
      setError('');
      setRaw(''); // clear source text once summarized
    } catch(e){
      setSummary(null);
      setError(String(e.message).slice(0,180));
    }
  };
  return (
    <section role="dialog" aria-label="SPARK Phone and Watch Activity" aria-modal="false"
      className="fixed z-[110] top-16 right-4 md:right-8 w-[min(94vw,540px)] max-h-[80vh] overflow-y-auto bg-slate-950/95 border border-cyan-500/40 rounded-2xl shadow-2xl p-5 text-slate-100 backdrop-blur-xl text-sm"
      style={{WebkitAppRegion:'no-drag'}}>
      <div className="flex justify-between gap-3 border-b border-cyan-900/70 pb-3">
        <div>
          <h2 className="flex items-center gap-2 font-bold text-lg text-cyan-300"><Smartphone size={20}/> PHONE / WATCH</h2>
          <p className="text-slate-300 mt-1">Android Health Connect — seven-day activity reader</p>
        </div>
        <button type="button" aria-label="Close Phone and Watch" onClick={onClose}
          className="p-2 rounded-lg border border-slate-700 hover:bg-slate-800"><X size={18}/></button>
      </div>
      <div className="mt-4 p-3 rounded-xl border border-slate-700 bg-slate-900/70">
        <h3 className="flex items-center gap-2 font-semibold text-cyan-200"><Watch size={17}/>Garmin fēnix 7 pathway</h3>
        <p className="text-slate-300 mt-2 leading-relaxed">
          Sync your watch with Garmin Connect on Android 14+. Enable Garmin Connect's
          one-way sharing to Health Connect, then grant SPARK Companion permission
          to read exercise sessions, steps and distance. Activity totals may also
          include other apps or your phone.
        </p>
        <p className="mt-2 text-amber-200 font-medium">Not a live Bluetooth pairing. No automatic PC sync or verified Garmin-only totals.</p>
      </div>
      <div className="mt-4 p-3 rounded-xl border border-cyan-900/70 bg-cyan-950/20">
        <h3 className="font-semibold text-cyan-200">USB phone pairing — local-only preview</h3>
        <p className="mt-2 text-xs text-slate-300">Connect a phone with trusted USB debugging and Android platform-tools. In PowerShell run:</p>
        <code className="block mt-2 text-xs rounded bg-slate-950 p-2 select-all">adb reverse tcp:38177 tcp:38177</code>
        <div className="flex gap-2 mt-3">
          <button type="button" disabled={usb.listening} onClick={()=>changeUsb('start')}
            className="px-3 py-2 rounded bg-cyan-800 hover:bg-cyan-700 disabled:opacity-50">Start USB pairing</button>
          <button type="button" disabled={!usb.listening} onClick={()=>changeUsb('stop')}
            className="px-3 py-2 rounded border border-slate-600 disabled:opacity-50">Stop / revoke</button>
        </div>
        <div className="mt-3 rounded border border-slate-700 bg-slate-950/50 p-3">
          <p className="font-semibold text-cyan-200">SPARK Mobile AI — separate desktop approval</p>
          <p className="text-xs text-slate-300 mt-1">Enable optional read-only AI answers to paired Android. Mobile text may be sent by your PC to its existing Gemini or Groq provider. This does not grant file, browser, agent, email, purchase or business-write controls, and does not add a paid subscription.</p>
          <button type="button" disabled={!usb.listening}
            onClick={toggleMobileAi}
            className="mt-2 px-3 py-2 rounded border border-cyan-700 disabled:opacity-50">
            {usb.aiEnabled?'Disable mobile AI replies':'Enable AI replies to Android'}
          </button>
          <p role="status" className="mt-2 text-xs text-slate-300">
            {usb.aiEnabled?'Mobile AI read-only replies permitted until revoked or session expiry.':'Mobile AI OFF. Pairing alone cannot use desktop AI.'}
          </p>
        </div>
        <div className="mt-3 rounded border border-slate-700 bg-slate-950/50 p-3">
          <p className="font-semibold text-cyan-200">Personal notes & tasks — separate sync approval</p>
          <p className="mt-1 text-xs text-slate-300">Allow the paired Android app to merge up to 100 notes and 100 checklist items with SPARK's app-private Windows storage. Sync happens only when you tap it on Android. It keeps the union of records; deletions are not propagated and completed tasks stay completed. Stored personal text is not separately encrypted. Never sync passwords or company secrets.</p>
          <button type="button" disabled={!usb.listening}
            onClick={togglePersonalSync}
            className="mt-2 px-3 py-2 rounded border border-cyan-700 disabled:opacity-50">
            {usb.syncEnabled?'Disable personal notes/tasks sync':'Enable personal notes/tasks sync'}
          </button>
          <p className="mt-2 text-xs text-slate-400">{usb.syncEnabled
            ? 'Personal sync permitted until revoked or the panel closes.'
            : 'Personal sync OFF. Pairing alone does not share notes or tasks.'}</p>
        </div>
        {usb.listening&&!usb.paired&&usb.code&&
          <p className="mt-3 text-slate-200">Enter this one-time code in the Android companion:
            <strong className="block mt-1 text-2xl tracking-widest text-cyan-300 select-all">{usb.code}</strong>
            <span className="text-xs text-slate-400">Expires after 2 minutes. Restart pairing if expired.</span>
          </p>}
        {usb.listening&&usb.paired&&<p className="mt-3 text-emerald-300">Android paired. Health summary transfer, AI replies and personal notes/tasks sync require their respective on-phone actions and desktop permissions.</p>}
        {usbNotice&&<p role="status" className="mt-2 text-xs text-slate-300">{usbNotice}</p>}
        <p className="mt-2 text-xs text-amber-200">This is not wireless pairing or phone control. The listener is confined to PC localhost; USB forwarding is temporary. Disconnect USB debugging when finished.</p>
      </div>
      <ol className="mt-4 list-decimal pl-5 text-slate-200 space-y-2">
        <li>Install the SPARK Companion Android debug APK after the Android build succeeds.</li>
        <li>Open the companion and tap <strong>Connect Health Connect</strong> to grant read-only access.</li>
        <li>Choose either manual Copy / Share, or pair through USB and explicitly Send summary to SPARK PC.</li>
        <li>For manual import, paste the summary below and select <strong>Import summary</strong>.</li>
      </ol>
      <label htmlFor="spark-android-summary" className="block mt-5 font-semibold text-cyan-300">
        Paste summary (private, not sent to cloud)
      </label>
      <textarea id="spark-android-summary" rows={5} maxLength={10000} value={raw}
        onChange={e=>setRaw(e.target.value)}
        placeholder={'Last 7 days\n\nActivities: 3\nSteps: 12,345\nDistance: 56.78 km\n\nSource apps: com.example.fitness\n\nHealth Connect totals may include non-Garmin sources.'}
        className="mt-2 w-full rounded-xl bg-slate-900 p-3 border border-slate-700 focus:border-cyan-400 text-slate-100 outline-none text-sm" />
      <div className="flex gap-3 mt-3">
        <button type="button" onClick={load} disabled={!raw.trim()}
          className="px-4 py-2 bg-cyan-800 hover:bg-cyan-700 font-semibold rounded-lg disabled:opacity-50 flex items-center gap-2">
          <ClipboardPaste size={16}/> Import summary
        </button>
        <button type="button" className="px-4 py-2 border border-slate-600 rounded-lg" onClick={()=>{setRaw('');setSummary(null);setError('');}}>
          Clear
        </button>
      </div>
      {error&&<p className="mt-3 text-amber-200" role="alert">{error}</p>}
      {summary&&<div className="mt-4 rounded-xl p-4 border border-cyan-800 bg-cyan-950/20">
        <h3 className="font-semibold text-cyan-200 flex items-center gap-2"><Activity size={16}/>Imported Health Connect snapshot</h3>
        <p className="text-xs text-slate-400 mt-1">Seven-day aggregate, from a user-shared text summary</p>
        <div className="grid grid-cols-3 gap-2 mt-4 text-center">
          <div><strong className="text-xl">{summary.activities}</strong><div className="text-xs text-slate-300">Activities</div></div>
          <div><strong className="text-xl">{summary.steps.toLocaleString('en-US')}</strong><div className="text-xs text-slate-300">Steps</div></div>
          <div><strong className="text-xl">{summary.distanceKm.toFixed(2)}</strong><div className="text-xs text-slate-300">km</div></div>
        </div>
        <div className="mt-4 text-xs text-slate-300">
          Exercise source apps: {summary.sources.length?summary.sources.join(', '):'None listed'}
        </div>
        <p className="mt-2 text-xs text-amber-200">{summary.note}</p>
      </div>}
      <p className="mt-4 text-xs text-slate-400 flex gap-2 items-start">
        <ShieldCheck size={16} className="shrink-0"/>
        Both manual and USB imports remain in this open panel's memory only and are discarded
        when it closes. No cloud upload, wireless phone control, direct watch pairing or automatic
        healthcare integration is performed.
      </p>
    </section>
  );
}
