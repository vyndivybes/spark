import React,{useEffect,useReducer,useState} from 'react';
import {Clock3,Pause,Play,RotateCcw,X,Plus,ShieldCheck} from 'lucide-react';
import {createFocusState,advanceFocus,formatFocusClock} from '../utils/focusClock.mjs';

/* This component MUST remain mounted while collapsed so user can focus
 * elsewhere in the cockpit without losing the session. No storage, camera,
 * active-app sampling, notification permission, AI calls or network requests.
 */
export default function FocusPanel({visible,onClose}){
 const [state,dispatch]=useReducer((current,action)=>advanceFocus(current,action,Date.now()),
   undefined,()=>createFocusState(25));
 const [minutes,setMinutes]=useState(25);
 const [intent,setIntent]=useState('');
 const [error,setError]=useState('');
 useEffect(()=>{
   const timer=setInterval(()=>dispatch({type:'tick'}),1000);
   return ()=>clearInterval(timer);
 },[]);
 const act=(type,options={})=>{
   setError('');
   try{dispatch({type,...options});}
   catch(e){setError(String(e.message).slice(0,120));}
 };
 // validate BEFORE dispatch; errors thrown inside React reducer are not caught
 // by event handlers and would otherwise crash the cockpit.
 const start=()=>{
   if(!Number.isInteger(minutes)||minutes<1||minutes>240){
     setError('Choose a whole-number duration from 1 to 240 minutes.');
     return;
   }
   setError('');
   dispatch({type:'start',minutes});
 };
 const extend=()=>{
   if(state.durationSeconds+5*60>240*60){
     setError('A focus session cannot exceed four hours.');
     return;
   }
   setError('');
   dispatch({type:'extend',minutes:5});
 };
 if(!visible)return null;
 const active=state.phase==='running';
 const paused=state.phase==='paused';
 const busy=active||paused;
 const percent=Math.max(0,Math.min(100,100*(1-state.remainingSeconds/state.durationSeconds)));
 return(
  <section role="dialog" aria-modal="false" aria-label="SPARK Focus Mode"
   className="fixed z-[110] top-16 right-4 md:right-8 w-[min(95vw,490px)] max-h-[82vh] overflow-y-auto rounded-2xl border border-cyan-500/40 bg-slate-950/95 p-5 text-slate-100 backdrop-blur-xl shadow-2xl"
   style={{WebkitAppRegion:'no-drag'}}>
   <div className="flex items-start justify-between gap-3 border-b border-cyan-900 pb-4">
    <div>
     <h2 className="flex items-center gap-2 text-lg font-bold tracking-wide text-cyan-300">
      <Clock3 size={21}/> FOCUS MODE
     </h2>
     <p className="mt-1 text-sm text-slate-300">A lightweight, local focus timer for SPARK</p>
    </div>
    <button type="button" onClick={onClose} aria-label="Hide Focus Mode"
     className="rounded-lg border border-slate-700 p-2 hover:bg-slate-800"><X size={18}/></button>
   </div>
   <div className="text-center py-6">
    <div className="text-[64px] leading-none font-semibold font-mono tracking-tight text-cyan-100 tabular-nums"
      aria-live="off">{formatFocusClock(state.remainingSeconds)}</div>
    <div role="status" className="mt-3 text-sm text-slate-300">
     {state.phase==='completed'?'Session complete — well done.':
      active?'Focus session running':paused?'Session paused':'Ready to begin'}
    </div>
    <div className="mt-4 rounded-full h-2 bg-slate-800 overflow-hidden">
     <div className="h-full bg-cyan-500 transition-[width] duration-500"
       style={{width:percent+'%'}} />
    </div>
   </div>
   {!busy&&<div className="space-y-3">
     <label htmlFor="spark-focus-intent" className="block text-sm font-semibold text-slate-200">
       What are you working on? (optional)
     </label>
     <input id="spark-focus-intent" type="text" maxLength={120} value={intent}
      onChange={e=>setIntent(e.target.value)}
      placeholder="e.g. SPARK feature integration"
      className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100" />
     <label htmlFor="spark-focus-minutes" className="block text-sm font-semibold text-slate-200">
       Duration in minutes
     </label>
     <div className="flex flex-wrap gap-2">
       {[5,25,50].map(m=>(
        <button key={m} type="button" onClick={()=>setMinutes(m)}
         className={'rounded-lg border px-3 py-2 text-sm '+(minutes===m?
           'bg-cyan-800 border-cyan-500':'border-slate-700 hover:bg-slate-800')}>
         {m}m
        </button>
       ))}
       <input id="spark-focus-minutes" aria-label="Custom minutes"
        type="number" min="1" max="240" step="1" value={minutes}
        onChange={e=>setMinutes(e.target.value===''?0:Number(e.target.value))}
        className="w-20 rounded-lg border border-slate-700 bg-slate-900 px-2 py-2 text-slate-100" />
     </div>
   </div>}
   {busy && intent && <div className="rounded-xl border border-slate-700 bg-slate-900/80 px-3 py-2 text-sm text-cyan-200 break-words">
     Focus: {intent}
   </div>}
   <div className="mt-5 flex flex-wrap items-center gap-2">
     {!busy&&
       <button type="button" onClick={start}
        className="flex items-center gap-2 rounded-lg bg-cyan-800 px-4 py-2 font-semibold hover:bg-cyan-700">
        <Play size={16}/> Start focus
       </button>}
     {active&&<button type="button" onClick={()=>act('pause')}
       className="flex items-center gap-2 rounded-lg border border-cyan-600 px-4 py-2 hover:bg-cyan-900">
       <Pause size={16}/> Pause
     </button>}
     {paused&&<button type="button" onClick={()=>act('resume')}
       className="flex items-center gap-2 rounded-lg border border-cyan-600 px-4 py-2 hover:bg-cyan-900">
       <Play size={16}/> Resume
     </button>}
     {busy&&<button type="button" onClick={extend}
       className="flex items-center gap-2 rounded-lg border border-slate-600 px-4 py-2 hover:bg-slate-800">
       <Plus size={16}/> Add 5m
     </button>}
     {state.phase!=='idle'&&
      <button type="button" onClick={()=>{act('reset');setIntent('');}}
       className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 hover:bg-slate-800">
       <RotateCcw size={16}/> Reset
      </button>}
   </div>
   {error&&<p role="alert" className="mt-3 text-amber-200 text-sm">{error}</p>}
   <p className="mt-5 flex items-start gap-2 border-t border-slate-800 pt-4 text-sm text-slate-300">
    <ShieldCheck size={18} className="text-cyan-300 shrink-0"/>
    <span><strong>Timer only.</strong> This timer does not monitor apps or verify attention.
    It stays active when you hide this panel, but resets when SPARK closes.
    No focus data is uploaded or stored.</span>
   </p>
   <span hidden>{state.observationMode}</span>
  </section>
 );
}
