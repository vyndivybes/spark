import React from 'react';
import { Activity, X, RefreshCw, Copy, Download, ShieldCheck, Mic } from 'lucide-react';

/* Independent SPARK operational panel. No provider registration, key editing,
 * device capture, quota polling, or additional AI inference is performed. */
const value=(v)=>typeof v==='string'&&v!=='unknown'?v:'—';

export default function SystemCenter({
  diagnostics, socketConnected, muted, transcriptCount, onClose,
  onRefresh, onCopyReport, onSaveTranscript, notice
}) {
  const d=diagnostics||{};
  const connected=socketConnected && d.live_state==='connected';
  const handsFree=connected && d.audio_transport==='browser_aec' && d.hands_free_ready===true;
  const quota=d.live_error_code==='429';
  const rows=[
    ['Backend',socketConnected?'ONLINE':'OFFLINE'],
    ['AI provider',value(d.ai_provider)],
    ['Model',value(d.live_model)],
    ['Voice profile',value(d.live_profile)],
    ['AI session',value(d.live_state)],
    ['Audio engine',value(d.audio_transport)],
    ['Microphone',muted?'MUTED':'AVAILABLE'],
    ['Session uptime',Number.isFinite(d.uptime_seconds)?Math.floor(d.uptime_seconds/60)+' minutes':'—'],
  ];
  return (
    <section role="dialog" aria-label="SPARK Systems Center" aria-modal="false"
      className="fixed z-[110] top-16 right-4 md:right-8 w-[min(94vw,520px)] max-h-[82vh] overflow-y-auto
        bg-slate-950/95 border border-cyan-500/40 rounded-2xl shadow-2xl p-5 text-slate-100
        backdrop-blur-xl text-sm" style={{WebkitAppRegion:'no-drag'}}>
      <div className="flex items-start justify-between border-b border-cyan-900/70 pb-4 gap-2">
        <div>
          <div className="flex gap-2 text-cyan-300 font-bold tracking-wider items-center"><Activity size={20}/>
            SYSTEMS CENTER
          </div>
          <div className="text-slate-300 text-sm mt-1">Runtime health, audio readiness and session utilities</div>
        </div>
        <button type="button" aria-label="Close Systems Center" onClick={onClose}
          className="p-2 rounded-lg border border-slate-700 hover:bg-slate-800">
          <X size={17}/>
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 mt-4">
        <div className={'border rounded-xl p-3 '+(connected?'border-emerald-700/60 bg-emerald-950/30':'border-amber-800/60 bg-amber-950/20')}>
          <div className="text-xs text-slate-300">AI session</div>
          <div className="text-lg font-semibold mt-1">{connected?'CONNECTED':'NOT CONNECTED'}</div>
        </div>
        <div className={'border rounded-xl p-3 '+(handsFree?'border-emerald-700/60 bg-emerald-950/30':'border-amber-800/60 bg-amber-950/20')}>
          <div className="flex gap-1 items-center text-xs text-slate-300"><Mic size={13}/>Hands-free AEC</div>
          <div className="text-lg font-semibold mt-1">{handsFree?'READY':'NOT READY'}</div>
        </div>
      </div>

      {quota && <p role="alert" className="mt-4 rounded-lg border border-amber-700 bg-amber-950/40 p-3 text-amber-200">
        Last reported provider error was 429 (quota). This screen cannot reset or extend provider limits.
      </p>}

      <div className="mt-4 border border-slate-800 rounded-xl overflow-hidden">
        {rows.map(([name,state])=>(
          <div key={name} className="flex justify-between gap-3 p-2.5 border-b border-slate-800/70 last:border-0">
            <span className="text-slate-300">{name}</span>
            <span className="font-semibold text-slate-100 text-right break-all">{state}</span>
          </div>
        ))}
      </div>

      <p className="mt-3 text-xs text-slate-400">
        API quota balances are not available through this diagnostics panel. Groq cloud session
        status means the local voice pipeline is ready; an actual provider request verifies its key.
      </p>
      <div className="flex flex-wrap gap-2 mt-4">
        <button type="button" onClick={onRefresh}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cyan-700/60 hover:bg-cyan-950">
          <RefreshCw size={15}/> Refresh
        </button>
        <button type="button" onClick={onCopyReport}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cyan-700/60 hover:bg-cyan-950">
          <Copy size={15}/> Copy report
        </button>
      </div>

      <div className="mt-5 pt-4 border-t border-slate-700">
        <div className="flex items-center gap-2 font-semibold"><ShieldCheck size={17} className="text-cyan-300"/> Session export</div>
        <p className="text-slate-300 text-xs mt-2">
          Exports up to 200 recent messages and their source links. A file-save dialog
          appears first. Your conversation may contain private information.
        </p>
        <button type="button" onClick={onSaveTranscript} disabled={!transcriptCount}
          className="mt-3 flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-800 hover:bg-cyan-700
            font-semibold disabled:opacity-40 disabled:cursor-not-allowed">
          <Download size={16}/> Save transcript (.md)
        </button>
        <div className="mt-2 text-xs text-slate-400">{transcriptCount} messages in this session</div>
      </div>

      <div className="mt-4 pt-3 border-t border-slate-800 text-xs text-slate-400">
        Keyboard shortcut: Ctrl+Shift+M to toggle the microphone.
      </div>
      <p className="mt-3 text-sm text-cyan-200" role="status">{notice||''}</p>
    </section>
  );
}
