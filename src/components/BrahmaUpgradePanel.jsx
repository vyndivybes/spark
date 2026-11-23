import React,{useEffect,useRef,useState} from 'react';

const btn='rounded-lg border border-cyan-500/50 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-900/60 disabled:opacity-40';
const card='rounded-xl border border-cyan-700/40 bg-slate-950/60 p-4';

/** Owner-gated controls. Server permission checks remain authoritative. */
export default function BrahmaUpgradePanel({socket,project}) {
 const [candidates,setCandidates]=useState([]);
 const [memories,setMemories]=useState([]);
 const [rea,setRea]=useState([]);
 const [text,setText]=useState('');
 const [status,setStatus]=useState('Select a read-only report or request an explicitly approved action.');
 const [busy,setBusy]=useState(false);
 const pending=useRef(new Set());
 const seq=useRef(0);
 const request=(action,payload={})=>{
   if(!socket?.connected || !socket.workspaceToken){setStatus('Connect to the SPARK desktop workspace first.');return;}
   const request_id='brahma-'+(++seq.current);
   pending.current.add(request_id);setBusy(true);
   socket.emit('workspace_action',{request_id,workspace_token:socket.workspaceToken,project,action,payload});
 };
 useEffect(()=>{
  const onResult=(message)=>{
   if(!message||!pending.current.delete(message.request_id))return;
   setBusy(pending.current.size>0);
   if(!message.ok){setStatus(String(message.message||'Action rejected.'));return;}
   const result=message.result;
   if(message.action==='brahma_composition')setCandidates(result?.candidates||[]);
   if(message.action==='brahma_rea_discovery')setRea(result?.tool_names||[]);
   if(message.action==='brahma_memory_list')setMemories(Array.isArray(result)?result:[]);
   if(message.action==='brahma_memory_remember'){
     setText('');setStatus('Memory saved locally with an expiration and provenance.');
     request('brahma_memory_list');return;
   }
   if(message.action==='brahma_memory_forget'){request('brahma_memory_list');return;}
   if(message.action==='brahma_reflex')setStatus(result?.ok
     ?(result.execution==='none'?'Supported reflex commands listed in the response.':'Launch submitted; window visibility is not verified.')
     :'Reflex action rejected or failed: '+String(result?.error||result?.result?.error||'unknown'));
   else setStatus(message.action.replaceAll('_',' ')+' completed.');
  };
  socket?.on('workspace_result',onResult);
  return()=>{socket?.off('workspace_result',onResult);pending.current.clear();};
 },[socket,project]);
 return <section className="mt-4 space-y-3 text-slate-100" aria-label="Brahma-inspired SPARK upgrades">
  <header className={card}>
    <h3 className="text-lg font-semibold text-cyan-200">SPARK / REA Composition</h3>
    <p className="mt-1 text-sm text-slate-300">Original SPARK modules. No restricted Brahma code is imported, and static analysis is not operational proof.</p>
  </header>
  <div className={card}>
   <h4 className="font-semibold">Capability review and live REA discovery</h4>
   <div className="mt-3 flex gap-2 flex-wrap">
    <button type="button" className={btn} disabled={busy} onClick={()=>request('brahma_composition')}>Inspect 8 candidates</button>
    <button type="button" className={btn} disabled={busy} onClick={()=>request('brahma_rea_discovery')}>Discover REA tools</button>
   </div>
   {candidates.length>0&&<ul className="mt-3 space-y-2 text-sm">{candidates.map(c=><li key={c.feature} className="border-b border-white/10 pb-2"><strong>{c.feature.replaceAll('_',' ')}</strong> · priority {c.priority} · {c.risk} risk · {c.baseline}<p className="text-slate-400">{c.adaptation} · {c.reuse_policy}</p></li>)}</ul>}
   {rea.length>0&&<p className="mt-3 text-sm text-slate-300">Available REA tools (not executed): {rea.join(', ')}</p>}
  </div>
  <div className={card}>
   <h4 className="font-semibold">Explicit local memory</h4>
   <p className="text-xs text-slate-300">Project: {project}. Local unencrypted storage. Do not enter passwords, API keys or sensitive secrets. Entries expire after 30 days by default.</p>
   <label className="block mt-3 text-sm">Memory to save
    <input className="mt-1 w-full rounded-lg bg-slate-900 border border-cyan-700 p-2 text-white" maxLength={512}
      value={text} onChange={e=>setText(e.target.value)} placeholder="Remember a project preference (no secrets)"/>
   </label>
   <div className="flex flex-wrap gap-2 mt-2">
    <button type="button" className={btn} disabled={busy||!text.trim()} onClick={()=>request('brahma_memory_remember',{body:text})}>Remember explicitly</button>
    <button type="button" className={btn} disabled={busy} onClick={()=>request('brahma_memory_list')}>Review saved memories</button>
   </div>
   {memories.length>0&&<ul className="mt-3 space-y-2">{memories.map(m=><li key={m.id} className="border-b border-white/10 pb-2 text-sm"><p>{m.body}</p><small className="text-slate-400">{m.source} · confidence {m.confidence} · expires {new Date(m.expires_at*1000).toLocaleDateString()}</small><div><button type="button" className={btn} disabled={busy} onClick={()=>request('brahma_memory_forget',{id:m.id})}>Forget entry</button></div></li>)}</ul>}
  </div>
  <div className={card}>
   <h4 className="font-semibold">Deterministic PC reflex actions</h4>
   <p className="mt-1 text-xs text-slate-300">Launching applications requires active PC autonomy. No shell access or arbitrary executables are introduced.</p>
   <div className="flex flex-wrap gap-2 mt-2">
    <button type="button" className={btn} disabled={busy} onClick={()=>request('brahma_reflex',{command:'open calculator'})}>Open Calculator</button>
    <button type="button" className={btn} disabled={busy} onClick={()=>request('brahma_reflex',{command:'open notepad'})}>Open Notepad</button>
   </div>
  </div>
  <div className={card}>
   <h4 className="font-semibold">SPARK Android companion</h4>
   <p className="text-sm text-slate-300">Identity source scaffold exists. No APK or encrypted pairing transport has been qualified; remote commands remain disabled.</p>
  </div>
  <p role="status" className="rounded-lg border border-cyan-700/40 bg-cyan-950/40 p-3 text-sm text-cyan-100">{status}</p>
 </section>;
}
