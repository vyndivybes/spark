import React, {useState} from 'react';
import {Activity, X, Smartphone, Watch, ClipboardPaste, ShieldCheck} from 'lucide-react';
import {parseHealthConnectSummary} from '../utils/healthConnectSummary.mjs';

/* Explicit manual activity import only. No cloud upload, polling, storage,
 * direct Garmin login, Bluetooth pairing or sensitive sensor streaming.
 * ARKUS mobile sources are session-package names, not audited Garmin provenance.
 */
export default function HealthConnectPanel({onClose}) {
  const [raw,setRaw]=useState('');
  const [summary,setSummary]=useState(null);
  const [error,setError]=useState('');
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
      <ol className="mt-4 list-decimal pl-5 text-slate-200 space-y-2">
        <li>Install the SPARK Companion Android debug APK after the Android build succeeds.</li>
        <li>Open the companion and tap <strong>Connect Health Connect</strong> to grant read-only access.</li>
        <li>Tap <strong>Copy summary</strong> or <strong>Share activity summary</strong>. Transfer the text to this PC yourself.</li>
        <li>Paste the seven-day summary below and select <strong>Import summary</strong>.</li>
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
        Import remains in this open panel's memory only. It is discarded when the panel closes.
        No remote transfer, watch pairing or automatic healthcare integration is performed.
      </p>
    </section>
  );
}
