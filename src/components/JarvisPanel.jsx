import React,{useEffect,useRef,useState} from 'react';

/** Remote answers are read-only and never interpreted as device instructions. */
export default function JarvisPanel({socket,visible,onClose,authenticated=false}){
 const [question,setQuestion]=useState('');
 const [pending,setPending]=useState(false);
 const [reply,setReply]=useState(null);
 const current=useRef(null);
 useEffect(()=>{
  const receive=message=>{
   if(!message||message.request_id!==current.current)return;
   current.current=null;setPending(false);
   if(message.ok===true&&message.result?.status){
    setReply({status:message.result.status,answer:message.result.answer,
     sourceAuthority:message.result.sourceAuthority,sourceSystem:message.result.sourceSystem,
     observedAt:message.result.observedAt,dataCompleteness:message.result.dataCompleteness});
   }else setReply({status:'UNAVAILABLE',answer:message.message||'Jarvis is unavailable.'});
  };
  socket.on('jarvis_result',receive);
  const offline=()=>{current.current=null;setPending(false);setReply({status:'UNAVAILABLE',answer:'SPARK disconnected. No enterprise response is available.'})};
  socket.on('disconnect',offline);
  return()=>{socket.off('jarvis_result',receive);socket.off('disconnect',offline)};
 },[socket]);
 if(!visible)return null;
 const ask=event=>{
  event.preventDefault();
  if(!socket.connected||!authenticated||pending||question.trim().length<5||question.length>300)return;
  const requestId='jarvis-'+Date.now()+'-'+Math.random().toString(16).slice(2);
  current.current=requestId;setPending(true);setReply(null);
  socket.emit('jarvis_ask',{request_id:requestId,workspace_token:socket.workspaceToken,question:question.trim()});
 };
 return <section role="dialog" aria-label="SPARK Jarvis bridge" id="spark-jarvis-panel"
   className="fixed top-16 right-4 z-[120] w-[min(95vw,540px)] max-h-[78vh] overflow-auto rounded-2xl border border-cyan-600/50 bg-slate-950/95 p-5 text-slate-100 shadow-2xl backdrop-blur-xl"
   style={{WebkitAppRegion:'no-drag'}}>
   <div className="flex justify-between items-start gap-4">
    <div><h2 className="text-lg font-bold tracking-wide text-cyan-200">JARVIS · Enterprise Bridge</h2>
     <p className="mt-1 text-sm text-slate-300">Read-only VAOS intelligence. Business actions cannot be authorized here.</p></div>
    <button type="button" aria-label="Close Jarvis" onClick={onClose} className="rounded-md px-2 py-1 hover:bg-slate-800">✕</button>
   </div>
   <form onSubmit={ask} className="mt-4 space-y-2">
    <label htmlFor="jarvis-question" className="block text-sm text-slate-200">Ask Jarvis about enterprise records or a mission</label>
    <textarea id="jarvis-question" rows={3} maxLength={300} value={question}
     onChange={e=>setQuestion(e.target.value)} placeholder="How many inventory items are recorded?"
     className="w-full rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm text-white"/>
    <button type="submit" disabled={!socket.connected||!authenticated||pending||question.trim().length<5||!socket.workspaceToken}
      className="rounded-lg border border-cyan-500/60 px-4 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-40">
      {pending?'Consulting Jarvis…':'Ask Jarvis'}</button>
   </form>
   {!socket.connected&&<p className="mt-3 text-sm text-amber-300">SPARK backend offline.</p>}
   {reply&&<div className="mt-4 rounded-lg border border-slate-700 p-3 text-sm" aria-live="polite">
     <p className="font-semibold text-cyan-200">{reply.status}</p>
     <p className="mt-2 whitespace-pre-wrap">{reply.answer}</p>
     <p className="mt-3 text-xs text-slate-400">Source: {reply.sourceSystem||'Not evidenced'}
       {reply.sourceAuthority?' · '+reply.sourceAuthority:''}</p>
     {reply.observedAt&&<p className="mt-1 text-xs text-slate-400">Observed: {reply.observedAt}</p>}
     {reply.dataCompleteness&&<p className="mt-1 text-xs text-amber-200">Coverage: {reply.dataCompleteness}</p>}
   </div>}
 </section>;
}
