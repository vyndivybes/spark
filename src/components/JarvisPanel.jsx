import React,{useEffect,useState} from 'react';
import {X} from 'lucide-react';
import PcTaskReview from './PcTaskReview';

export default function JarvisPanel({onClose,invoke,socket,project}){
    const [state,setState]=useState(null);
    const [question,setQuestion]=useState('What is the current digital workforce status?');
    const [answer,setAnswer]=useState(null);
    const [notice,setNotice]=useState('Sign in directly to VAOS, then ask Jarvis a question.');
    const [busy,setBusy]=useState(false);
    const run=async(action)=>{
        setBusy(true);
        try{
            const result=await invoke({action,...(action==='ask'?{question}:{})});
            if(action==='status')setState(result);
            if(action==='ask'){setAnswer(result);setNotice(result.ok?'VAOS advisory received. No business action was executed.':result.message);}
            if(action==='open')setNotice('Sign in to VAOS in its window, then return here and refresh the connection.');
            if(action==='disconnect'){setState(null);setAnswer(null);setNotice('VAOS session removed from Spark.');}
        }catch(error){setNotice(String(error?.message||'Jarvis connection failed.'));}
        finally{setBusy(false);}
    };
    useEffect(()=>{let active=true;invoke({action:'status'}).then(result=>{if(active)setState(result);}).catch(()=>{});return()=>{active=false;};},[invoke]);
    return <section role="dialog" aria-label="VAOS Jarvis connection" className="fixed z-[115] top-16 right-4 w-[min(95vw,720px)] max-h-[85vh] overflow-y-auto rounded-2xl border border-cyan-500/40 bg-slate-950 p-5 text-slate-100 shadow-2xl" style={{WebkitAppRegion:'no-drag'}}>
        <header className="flex items-start justify-between gap-3"><div><h2 className="text-xl font-semibold text-cyan-200">VAOS Jarvis</h2><p className="mt-1 text-sm text-slate-400">Founder intelligence from your signed-in VAOS workspace.</p></div><button type="button" onClick={onClose} aria-label="Close Jarvis panel"><X size={20}/></button></header>
        <p className="mt-4 break-words text-xs text-slate-400">{state?.origin||'VAOS connection'} · {state?.sessionPresent?'Session present; verified on each question':'Sign-in required'}</p>
        <div className="my-4 flex flex-wrap gap-2">
            <button type="button" disabled={busy} className="rounded border border-cyan-500/50 px-3 py-2 text-sm" onClick={()=>run('open')}>Open VAOS / sign in</button>
            <button type="button" disabled={busy} className="rounded border border-slate-600 px-3 py-2 text-sm" onClick={()=>run('status')}>Refresh connection</button>
            <button type="button" disabled={busy} className="rounded border border-slate-600 px-3 py-2 text-sm" onClick={()=>run('disconnect')}>Disconnect VAOS</button>
        </div>
        <form onSubmit={event=>{event.preventDefault();run('ask');}}>
            <label className="block text-sm" htmlFor="jarvis-question">Ask Jarvis</label>
            <textarea id="jarvis-question" value={question} onChange={event=>setQuestion(event.target.value)} minLength={5} maxLength={300} required rows={3} className="mt-2 w-full rounded border border-slate-600 bg-slate-900 p-3 text-sm"/>
            <button type="submit" disabled={busy} className="mt-2 rounded bg-cyan-800 px-4 py-2 text-sm">{busy?'Working…':'Ask VAOS Jarvis'}</button>
        </form>
        <p role="status" className="my-4 text-sm text-amber-200">{notice}</p>
        {answer?.ok&&<article aria-label="Jarvis advisory answer" className="whitespace-pre-wrap rounded border border-slate-700 bg-slate-900 p-4 text-sm leading-relaxed">{answer.answer}<footer className="mt-4 text-xs text-slate-400">{answer.sourceSystem} · {answer.status} · Advisory only</footer></article>}
        {answer?.ok&&<PcTaskReview socket={socket} project={project} advice={answer.answer}/>}
        <p className="mt-4 text-xs leading-relaxed text-slate-400">Or say “Ask Jarvis, what is the current workforce status?” during a Spark voice session. Questions reach VAOS; voice replies also reach the active AI provider. PC autonomy does not grant business authority in VAOS.</p>
    </section>;
}
