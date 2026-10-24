import React,{useEffect,useRef,useState} from 'react';
const button='rounded-lg border border-cyan-600/50 px-3 py-2 text-sm disabled:opacity-40';
const input='w-full rounded-lg border border-white/20 bg-slate-900 p-2 text-sm';
export default function ReaWorkflowPanel({socket,project}){
 const [tools,setTools]=useState([]),[tool,setTool]=useState(''),[args,setArgs]=useState('{}'),[title,setTitle]=useState('REA teardown'),[reports,setReports]=useState([]),[report,setReport]=useState(null),[notice,setNotice]=useState('Inspect → retain report → build original notes → browser test → open'),[busy,setBusy]=useState(false);
 const [parts,setParts]=useState({});
 const [kind,setKind]=useState('website'),[target,setTarget]=useState(''),[goal,setGoal]=useState(''),[draft,setDraft]=useState(''),[status,setStatus]=useState(null);
 const pending=useRef(null),timer=useRef(null);
 const request=(action,payload={})=>{
  if(pending.current)return;
  if(!socket?.connected){setNotice('Connect the SPARK cockpit first.');return;}
  const id='rea-flow-'+Date.now();pending.current=id;setBusy(true);
  socket.emit('workspace_action',{workspace_token:socket.workspaceToken,request_id:id,action,project,payload});
  timer.current=setTimeout(()=>{pending.current=null;setBusy(false);setNotice('Request timed out; inspect saved reports before retrying.');},160000);
 };
 useEffect(()=>{
  setReport(null);setReports([]);setTools([]);setTool('');pending.current=null;setBusy(false);
  const receive=data=>{
   if(data?.request_id!==pending.current)return;pending.current=null;clearTimeout(timer.current);setBusy(false);
   if(!data.ok){setNotice(data.message||'Operation failed.');return;}
   if(data.action==='rea_discover')setTools(data.result);
   else if(data.action==='rea_workflow_status')setStatus(data.result);
   else if(data.action==='rea_workflow_list')setReports(data.result);
   else if(data.action!=='rea_workflow_speak'){setReport(data.result);setParts({});setDraft(data.result?.blueprint?JSON.stringify(data.result.blueprint,null,2):'');}
   setNotice('Completed. Review the saved result.');
  };
  socket?.on('workspace_result',receive);return()=>{socket?.off('workspace_result',receive);clearTimeout(timer.current);};
 },[socket,project]);
 async function preview(action){
  try{setBusy(true);const ipc=window.require?.('electron')?.ipcRenderer;if(!ipc)throw Error('Preview requires the SPARK desktop app.');
   const result=await ipc.invoke('spark:rea-preview',{action,project,id:report.id});setNotice(JSON.stringify(result));
  }catch(e){setNotice(e.message);}finally{setBusy(false);}
 }
 return <section className="lg:col-span-2 rounded-xl border border-cyan-400/30 p-4 space-y-3" aria-label="REA rebuild workflow">
  <h3 className="text-xl font-semibold">REA · understand and rebuild</h3>
  <p>Analyze an exact target, retain its teardown and build an original local app. Notes and validated data-app blueprints use first-party renderers. Optional model generation uses a verified zero-price route with explicit sharing approval.</p>
  <button className={button} disabled={busy} onClick={()=>request('rea_workflow_status')}>Check analysis and free-model readiness</button>
  {status&&<p role="status">Free-model key: {status.key_configured?'configured':'not configured'}; browser endpoint: {status.cdp_configured?'configured':'not configured'}. {status.policy}</p>}
  <label>Target type<select className={input} value={kind} onChange={e=>setKind(e.target.value)}><option value="website">Existing public website tab</option><option value="artifact">Local app package or binary</option></select></label>
  <input className={input} aria-label="Automatic analysis target" value={target} onChange={e=>setTarget(e.target.value)} placeholder={kind==='website'?'https://example.com/ already open in configured browser':'Absolute artifact path within host-approved REA roots'}/>
  <button className={button} disabled={busy||!target.trim()} onClick={()=>{if(window.confirm('Passively analyze this exact target and retain its sanitized evidence? '+target))request('rea_workflow_analyze',{kind,target:target.trim()});}}>Analyze selected target automatically</button>
  <button className={button} disabled={busy} onClick={()=>request('rea_discover')}>Discover analysis tools</button>
  <select aria-label="Workflow REA tool" className={input} value={tool} onChange={e=>setTool(e.target.value)}><option value="">Choose an installed tool</option>{tools.map(t=><option key={t.name} value={t.name}>{t.name}</option>)}</select>
  {tool&&<details><summary>Target argument schema</summary><pre className="overflow-auto max-h-52 text-xs">{JSON.stringify(tools.find(t=>t.name===tool)?.inputSchema,null,2)}</pre></details>}
  <input className={input} aria-label="Teardown title" value={title} onChange={e=>setTitle(e.target.value)}/>
  <textarea className={input} aria-label="Workflow target arguments" value={args} onChange={e=>setArgs(e.target.value)}/>
  <button className={button} disabled={busy||!tool} onClick={()=>{try{const argumentsValue=JSON.parse(args);if(window.confirm(`Analyze the displayed target using ${tool} and retain its sanitized evidence?\n${args}`))request('rea_workflow_create',{name:tool,arguments:argumentsValue,title});}catch{setNotice('Enter valid JSON arguments.');}}}>Analyze and save teardown</button>
  <button className={button} disabled={busy} onClick={()=>request('rea_workflow_list')}>Load saved reports</button>
  {reports.map(r=><button className={button} key={r.id} disabled={busy} onClick={()=>request('rea_workflow_read',{id:r.id})}>{r.title}</button>)}
  {report?.sections&&<article><h4 className="font-semibold">{report.title}</h4><p>Report {report.id} · {report.state}</p>
   {report.sections.map((s,i)=><details key={i}><summary>{i+1}. {s.title}</summary><pre className="whitespace-pre-wrap max-h-64 overflow-auto text-sm">{s.text}</pre><label>Narration part <select value={parts[i]||0} onChange={e=>setParts(p=>({...p,[i]:Number(e.target.value)}))}>{Array.from({length:Math.ceil((s.title.length+2+s.text.length)/400)},(_,part)=><option key={part} value={part}>{part+1}</option>)}</select></label><button className={button} disabled={busy} onClick={()=>request('rea_workflow_speak',{id:report.id,section:i,part:parts[i]||0})}>Read selected part aloud</button></details>)}
   <label>Original app goal<textarea className={input} aria-label="Original app goal" value={goal} onChange={e=>setGoal(e.target.value)} placeholder="Describe your original data app, users, fields and expected behavior"/></label>
   <button className={button} disabled={busy||goal.trim().length<10} onClick={()=>{if(window.confirm('Share up to 6000 characters of this sanitized report and your goal with OpenRouter free models? Pricing must verify zero; no paid fallback.'))request('rea_workflow_generate',{id:report.id,goal:goal.trim(),consent:true});}}>Generate blueprint using verified free model</button>
   <details><summary>Supply or edit a blueprint without inference</summary><p>JSON: title, description, entities and limitations. Entities contain key, label and fields; each field has key, label, type, required and options. Supported types: text, number, date, boolean, select. No code, URLs or integrations.</p><button className={button} disabled={busy} onClick={()=>setDraft(JSON.stringify({title:'Original Inventory',description:'Local stock records with quantities and status.',entities:[{key:'stock',label:'Stock',fields:[{key:'name',label:'Part name',type:'text',required:true,options:[]},{key:'quantity',label:'Quantity',type:'number',required:true,options:[]},{key:'state',label:'State',type:'select',required:true,options:['Available','Quarantine']}]}],limitations:['Local records only; no accounting, external sync or purchasing.']},null,2))}>Start a local inventory blueprint</button><textarea className={input} rows={8} aria-label="Original app blueprint JSON" value={draft} onChange={e=>setDraft(e.target.value)}/><button className={button} disabled={busy||!draft} onClick={()=>{try{request('rea_workflow_blueprint',{id:report.id,blueprint:JSON.parse(draft)});}catch{setNotice('Enter valid blueprint JSON.');}}}>Save as a separate blueprint candidate</button></details>
   <div className="flex flex-wrap gap-2 mt-3"><button className={button} disabled={busy} onClick={()=>request('rea_workflow_index',{id:report.id})}>Add report to searchable knowledge</button><button className={button} disabled={busy||Boolean(report.blueprint)} onClick={()=>request('rea_workflow_build',{id:report.id,recipe:'notes'})}>Build original notes app</button>{report.blueprint&&<button className={button} disabled={busy} onClick={()=>request('rea_workflow_build',{id:report.id,recipe:'blueprint'})}>Build blueprint app</button>}<button className={button} disabled={busy||report.state!=='staged'} onClick={()=>preview('test')}>Test in hidden browser</button><button className={button} disabled={busy||report.state!=='staged'} onClick={()=>preview('open')}>Open tested app</button></div>
   <p className="text-sm mt-2">Voice: “show REA reports”, “read REA report {report.id} section 1”, “build notes from REA report {report.id}”, “test REA app {report.id}”, “open REA app {report.id}”. You may say latest REA report or latest REA app instead of an ID. Report reading uses the existing local Windows speech path in Groq mode.</p>
  </article>}
  <p role="status">{notice}</p>
 </section>;
}
