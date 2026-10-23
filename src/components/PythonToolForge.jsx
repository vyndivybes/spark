import React,{useEffect,useRef,useState} from 'react';
const button='rounded-lg border border-cyan-500/40 bg-cyan-950/50 px-3 py-2 text-sm disabled:opacity-40';
const input='w-full rounded-lg border border-white/20 bg-slate-950 p-2 text-sm';
export default function PythonToolForge({socket,project}){
 const [goal,setGoal]=useState('');const [rows,setRows]=useState([]);const [policy,setPolicy]=useState({enabled:false,auto_forge:false});
 const [notice,setNotice]=useState('Load runtime status before running tools.');const [busy,setBusy]=useState(false);
 const [draft,setDraft]=useState('');const [inputs,setInputs]=useState('{}');const [result,setResult]=useState(null);
 const [autonomy,setAutonomy]=useState(null);const requests=useRef(new Map());const timer=useRef();
 function request(action,payload={}){
  if(!socket?.connected){setNotice('Spark backend is offline.');return;}
  const id=`pythonforge-${Date.now()}-${Math.random().toString(36).slice(2)}`;requests.current.set(id,action);setBusy(true);
  socket.emit('workspace_action',{workspace_token:socket.workspaceToken,request_id:id,action,project,payload});
  clearTimeout(timer.current);timer.current=setTimeout(()=>{setBusy(false);setNotice('Operation still pending. Check progress before retrying.');},300000);
 }
 useEffect(()=>{
  requests.current.clear();setRows([]);setResult(null);setPolicy({enabled:false,auto_forge:false});
  const receive=data=>{
   if(!requests.current.has(data?.request_id))return;
   requests.current.delete(data.request_id);clearTimeout(timer.current);setBusy(false);
   if(!data.ok){setNotice(data.message||'Operation failed.');return;}
   const value=data.result;setNotice('Completed. Review the result.');
   if(['python_tools_policy','configure_python_tools'].includes(data.action)){setPolicy(value);request('list_python_tools');}
   else if(data.action==='list_python_tools')setRows(value);
   else if(data.action.startsWith('saee_autonomy_'))setAutonomy(value);
   else if(value?.id&&value?.source){setRows(list=>[value,...list.filter(r=>r.id!==value.id).map(r=>value.status==='active'&&r.name===value.name&&r.status==='active'?{...r,status:'inactive'}:r)]);setResult(value);}
   else setResult(value);
  };
  socket?.on('workspace_result',receive);
  if(socket?.connected)request('python_tools_policy');
  return()=>{socket?.off('workspace_result',receive);clearTimeout(timer.current);};
 },[socket,project]);
 function parse(text){try{return JSON.parse(text);}catch{setNotice('Enter valid JSON.');return undefined;}}
 return <section className="rounded-xl border border-violet-400/40 bg-slate-950/70 p-4 space-y-3" aria-label="Full Python tool forge">
  <h3 className="text-xl font-semibold">Python tools · invent, test, register, run</h3>
  <p className="text-sm text-slate-300">These tools support Python imports and API calls and run with your Windows user permissions. They are not confined to a security sandbox. Review source, packages, environment names and expected-result tests before approving execution.</p>
  <div className="flex flex-wrap gap-2">
   <button className={button} disabled={busy} onClick={()=>request('python_tools_policy')}>Load tools and policy</button>
   <button className={button} disabled={busy} onClick={()=>{if(window.confirm('Enable trusted Python tools and automatic invention for your explicit voice/chat goals? Tools run as your Windows user. Packages and credential environment still require review.'))request('configure_python_tools',{enabled:true,auto_forge:true});}}>Enable automatic invention</button>
   <button className={button} onClick={()=>request('configure_python_tools',{enabled:false,auto_forge:false})}>Stop Python tools</button>
  </div>
  <p>Python runtime: {policy.enabled?'enabled':'disabled'} · Automatic invention: {policy.auto_forge?'enabled':'disabled'}</p>
  <textarea className={input} aria-label="Python tool goal" value={goal} onChange={e=>setGoal(e.target.value)} placeholder="Describe the missing tool, JSON inputs, expected outputs and API if needed"/>
  <button className={button} disabled={busy||goal.trim().length<10} onClick={()=>request('generate_python_tool',{description:goal.trim()})}>Generate Python tool</button>
  <details><summary>Edit source, requirements and tests</summary><textarea className={input} rows={10} aria-label="Python tool specification" value={draft} onChange={e=>setDraft(e.target.value)}/><button className={button} disabled={busy||!draft.trim()} onClick={()=>{const spec=parse(draft);if(spec)request('propose_python_tool',{spec});}}>Save revision</button></details>
  <label className="block">Run inputs (JSON)<textarea className={input} aria-label="Python tool inputs" value={inputs} onChange={e=>setInputs(e.target.value)}/></label>
  {rows.map(row=><article key={row.id} className="rounded-lg border border-white/15 p-3 space-y-2">
   <h4 className="font-semibold">{row.name} · {row.status}</h4><p>{row.description}</p>
   <details><summary>Source, expected tests and access</summary><pre className="max-h-96 overflow-auto text-xs whitespace-pre-wrap">{JSON.stringify(row,null,2)}</pre></details>
   <div className="flex flex-wrap gap-2">
    <button className={button} disabled={busy||!policy.enabled} onClick={()=>{if(window.confirm(`Execute ${row.name}'s tests as your OS user, prepare its declared packages and pass its declared environment variables?`))request('test_python_tool',{id:row.id,approved:true});}}>Test tool</button>
    <button className={button} disabled={busy||row.status!=='rejected'} onClick={()=>request('repair_python_tool',{id:row.id})}>Repair failed source</button>
    <button className={button} disabled={busy||row.status!=='tested'} onClick={()=>{if(window.confirm(`Activate reviewed tool ${row.name} for voice/chat and re-run its tests?`))request('activate_python_tool',{id:row.id,approved:true});}}>Register tool</button>
    <button className={button} disabled={busy||row.status!=='active'} onClick={()=>{const value=parse(inputs);if(value!==undefined)request('run_python_tool',{id:row.id,inputs:value});}}>Run</button>
    <button className={button} disabled={busy||row.status!=='active'} onClick={()=>request('deactivate_python_tool',{id:row.id})}>Deactivate</button>
    <button className={button} onClick={()=>setDraft(JSON.stringify({name:row.name,description:row.description,source:row.source,tests:row.tests,requirements:row.requirements,environment:row.environment},null,2))}>Revise</button>
   </div>
  </article>)}
  <p role="status">{notice}</p>{result&&<pre className="max-h-64 overflow-auto text-xs whitespace-pre-wrap" aria-label="Python tool result">{JSON.stringify(result,null,2)}</pre>}
  <details><summary>Background source patching</summary>
   <p className="text-sm">The scheduler stages changes, runs regression tests, activates passing patches, and checks health. Recovery and authorization code stays protected.</p>
   <div className="flex flex-wrap gap-2"><button className={button} disabled={busy} onClick={()=>request('saee_autonomy_status')}>Check background status</button><button className={button} disabled={busy} onClick={()=>{if(window.confirm('Enable background model-assisted source patching through staged regression tests and rollback?'))request('saee_autonomy_configure',{enabled:true,allow_model_source:true});}}>Enable background patching</button><button className={button} onClick={()=>request('saee_autonomy_stop')}>Stop background patching</button></div>
   {autonomy&&<pre className="max-h-48 overflow-auto text-xs whitespace-pre-wrap">{JSON.stringify(autonomy,null,2)}</pre>}
  </details>
 </section>;
}
