import React,{useEffect,useRef,useState} from 'react';

export default function PcTaskReview({socket,project,advice}){
    const [goal,setGoal]=useState('Save this Jarvis advisory for local follow-up');
    const [plan,setPlan]=useState('');
    const [task,setTask]=useState(null);
    const [history,setHistory]=useState([]);
    const [busy,setBusy]=useState(false);
    const [notice,setNotice]=useState('Prepare a draft first. Nothing executes until you approve its exact steps.');
    const pending=useRef(null),timer=useRef(null);
    const slug=String(project||'default').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,40).replace(/-+$/,'')||'default';
    useEffect(()=>{
        setTask(null);setPlan('');setHistory([]);
        setBusy(false);
        setNotice('Prepare a draft first. Nothing executes until you approve its exact steps.');
        const receive=data=>{
            if(data?.request_id!==pending.current)return;
            pending.current=null;clearTimeout(timer.current);setBusy(false);
            if(!data.ok){setNotice(data.message||'PC task request failed.');return;}
            if(data.action==='pc_task_history'){setHistory(data.result);setNotice('Local task history refreshed.');return;}
            setTask(data.result);setPlan(JSON.stringify(data.result.steps,null,2));
            setNotice(data.result.state==='awaiting_approval'?'Draft ready. Review every file path and command before approval.':'Task state: '+data.result.state);
        };
        socket?.on('workspace_result',receive);
        return()=>{clearTimeout(timer.current);pending.current=null;socket?.off('workspace_result',receive);};
    },[socket,slug,advice]);
    const send=(action,payload)=>{
        if(!socket?.connected){setNotice('Connect to Spark voice before staging or running a PC task.');return;}
        if(pending.current)return;
        const id='pc-review-'+crypto.randomUUID();pending.current=id;setBusy(true);
        setNotice(action==='pc_task_run'?'Running the approved plan. Turn off PC autonomy in Settings to block subsequent actions.':'Preparing local task data…');
        timer.current=setTimeout(()=>{pending.current=null;setBusy(false);setNotice('Request timed out. Refresh history before retrying an execution.');},action==='pc_task_run'?900000:15000);
        socket.emit('workspace_action',{workspace_token:socket.workspaceToken,request_id:id,action,project:slug,payload});
    };
    return <section className="mt-5 rounded-xl border border-amber-500/40 p-4" aria-label="Jarvis advisory to PC task">
        <h3 className="font-semibold text-amber-200">Prepare a local PC task</h3>
        <p className="mt-2 text-xs text-slate-400">The default draft saves this advisory as a Markdown report. You can edit the PC actions. Jarvis advice grants no execution authority; your approval applies to the displayed plan.</p>
        <label className="mt-3 block text-sm">Task goal<input className="mt-1 w-full rounded border border-slate-600 bg-slate-900 p-2" value={goal} maxLength={500} disabled={busy} onChange={e=>{setGoal(e.target.value);setTask(null);}}/></label>
        <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" disabled={busy} className="rounded border border-amber-500/50 px-3 py-2 text-sm" onClick={()=>send('pc_task_prepare',{goal,advice,steps:null})}>Prepare report task</button>
            <button type="button" disabled={busy} className="rounded border border-slate-600 px-3 py-2 text-sm" onClick={()=>send('pc_task_history',{})}>Refresh task history</button>
        </div>
        {plan&&<><details className="mt-3"><summary className="cursor-pointer text-sm">Review / edit exact PC actions</summary><textarea aria-label="PC task steps" rows={10} value={plan} disabled={busy} onChange={e=>{setPlan(e.target.value);setTask(null);}} className="mt-2 w-full rounded bg-slate-900 p-3 font-mono text-xs"/><button type="button" disabled={busy} onClick={()=>{try{send('pc_task_prepare',{goal,advice,steps:JSON.parse(plan)});}catch{setNotice('Enter a valid JSON array of PC actions.');}}} className="mt-2 rounded border border-slate-600 px-3 py-2 text-sm">Stage edited plan</button></details>
        {task?.state==='awaiting_approval'&&<div className="mt-3 space-y-2">{task.steps.map((step,index)=><pre key={index} className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-900 p-3 text-xs">{index+1}. {step.action}{'\n'}{step.path||step.command}{step.destination?' → '+step.destination:''}{step.content!==undefined?'\n\n'+step.content:''}</pre>)}</div>}
        <button type="button" disabled={busy||task?.state!=='awaiting_approval'} className="mt-3 rounded bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40" onClick={()=>send('pc_task_run',{id:task.id,plan_hash:task.plan_hash,approved:true})}>Approve and run these steps</button></>}
        <p role="status" className="mt-3 text-sm text-amber-100">{notice}</p>
        {!!task?.results?.length&&<details className="mt-3"><summary>Saved execution results</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(task.results,null,2)}</pre></details>}
        {!!history.length&&<ul className="mt-3 space-y-2 text-xs text-slate-300">{history.slice(0,10).map(item=><li key={item.id}>{item.goal} · {item.state}</li>)}</ul>}
    </section>;
}
