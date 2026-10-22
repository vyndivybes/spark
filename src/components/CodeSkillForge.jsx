import React, {useEffect,useRef,useState} from 'react';
const button='rounded-lg border border-cyan-600/50 bg-cyan-950/50 px-3 py-2 text-sm disabled:opacity-40';
const input='w-full rounded-lg border border-white/20 bg-slate-900 p-2 text-sm';
export default function CodeSkillForge({socket,project}) {
    const [goal,setGoal]=useState('');
    const [analysis,setAnalysis]=useState('');
    const [repository,setRepository]=useState('https://github.com/titechprabhasolutions/Brahma-Ai-Evo');
    const [evidence,setEvidence]=useState('');
    const [skills,setSkills]=useState([]);
    const [busy,setBusy]=useState(false);
    const [notice,setNotice]=useState('Create, test, review and activate original code skills.');
    const [result,setResult]=useState(null);
    const [values,setValues]=useState('{}');
    const [tool,setTool]=useState('');
    const [tools,setTools]=useState([]);
    const [argumentsText,setArgumentsText]=useState('{}');
    const [draft,setDraft]=useState('');
    const pending=useRef(new Map());
    const timer=useRef();
    function request(action,payload={}) {
        if(!socket?.connected){setNotice('Spark backend is offline.');return;}
        const id=`codeforge-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        pending.current.set(id,action);setBusy(true);
        socket.emit('workspace_action',{workspace_token:socket.workspaceToken,request_id:id,action,project,payload});
        clearTimeout(timer.current);timer.current=setTimeout(()=>{setBusy(false);setNotice('Still waiting. Check the connection before retrying.');},155000);
    }
    useEffect(()=>{
        setSkills([]);setResult(null);setEvidence('');setAnalysis('');pending.current.clear();
        const receive=data=>{
            if(!pending.current.has(data?.request_id))return;
            pending.current.delete(data.request_id);clearTimeout(timer.current);setBusy(false);
            if(!data.ok){setNotice(data.message||'Operation failed.');return;}
            const value=data.result;
            setNotice('Completed. Review the evidence below.');
            if(data.action==='list_code_skills')setSkills(value);
            else if(data.action==='analyze_repository'){setAnalysis(value.id);setResult({analysis_id:value.id,summary:value.summary,opportunities:value.opportunities});}
            else if(data.action==='rea_discover')setTools(Array.isArray(value)?value:[]);
            else if(data.action==='capture_rea_evidence'){setEvidence(value.id);setResult(value);}
            else if(value?.id && value?.source){setSkills(rows=>[value,...rows.filter(r=>r.id!==value.id).map(r=>value.status==='active'&&r.name===value.name&&r.status==='active'?{...r,status:'inactive'}:r)]);setResult(value);}
            else setResult(value);
        };
        socket?.on('workspace_result',receive);
        return()=>{socket?.off('workspace_result',receive);clearTimeout(timer.current);};
    },[socket,project]);
    function parse(text){try{return JSON.parse(text);}catch{setNotice('Enter valid JSON.');return undefined;}}
    return <section className="rounded-xl border border-cyan-500/30 bg-slate-950/60 p-4 space-y-3" aria-label="Code skill forge">
        <h3 className="text-xl font-semibold">Invent a code skill</h3>
        <p className="text-sm text-slate-300">Spark writes Python data-processing functions, runs examples in a bounded worker, and stores revisions locally. Activate after reviewing the code and tests; no restart is needed. File, network and device actions use existing approved tools.</p>
        <textarea className={input} aria-label="Code skill goal" value={goal} onChange={e=>setGoal(e.target.value)} placeholder="Describe the missing capability, expected result and edge cases"/>
        <input className={input} aria-label="Reference repository" value={repository} onChange={e=>setRepository(e.target.value)} placeholder="Reference GitHub URL or absolute local source folder"/>
        <button className={button} disabled={busy||!repository.trim()||goal.trim().length<10} onClick={()=>request('analyze_repository',{repository:repository.trim(),goal:goal.trim(),reference_paths:[]})}>Study repository for this goal</button>
        <input className={input} aria-label="Repository analysis ID" value={analysis} onChange={e=>setAnalysis(e.target.value)} placeholder="Optional saved repository analysis ID"/>
        <input className={input} aria-label="REA evidence ID" value={evidence} onChange={e=>setEvidence(e.target.value)} placeholder="Optional retained REA evidence ID"/>
        <div className="flex flex-wrap gap-2">
            <button className={button} disabled={busy||goal.trim().length<10} onClick={()=>request('generate_code_skill',{description:goal.trim(),analysis_id:analysis.trim()||null,rea_evidence_id:evidence.trim()||null})}>Generate candidate</button>
            <button className={button} disabled={busy} onClick={()=>request('list_code_skills')}>Load saved skills</button>
        </div>
        <details><summary>Inspect an artifact with REA</summary>
            <p className="text-sm text-slate-300">Use source repository analysis for ordinary code. For binaries, packages and runtime evidence, discover a tool, inspect its schema and choose the exact target. REA tools may modify targets; execution requires an active authorized session.</p>
            <button className={button} disabled={busy} onClick={()=>request('rea_discover')}>Discover REA tools</button>
            <select aria-label="REA inspection tool" className={input} value={tool} onChange={e=>setTool(e.target.value)}><option value="">Select a tool</option>{tools.map(t=><option key={t.name} value={t.name}>{t.name}</option>)}</select>
            {tool&&<pre className="max-h-40 overflow-auto text-xs whitespace-pre-wrap">{JSON.stringify(tools.find(t=>t.name===tool)?.inputSchema,null,2)}</pre>}
            <textarea aria-label="REA inspection arguments" className={input} value={argumentsText} onChange={e=>setArgumentsText(e.target.value)}/>
            <button className={button} disabled={busy||!tool} onClick={()=>{const args=parse(argumentsText);if(args&&window.confirm(`Run REA tool ${tool} with the displayed arguments and retain its evidence?`))request('capture_rea_evidence',{name:tool,arguments:args});}}>Inspect and retain evidence</button>
        </details>
        <details><summary>Edit or propose skill code and tests</summary>
            <p className="text-sm">Paste a candidate JSON with name, description, source and tests. Source format: def run(inputs), using local assignments, if/else and returns. Each test has inputs and expected. Editing creates a new revision.</p>
            <textarea aria-label="Code skill specification" className={input} rows={8} value={draft} onChange={e=>setDraft(e.target.value)}/>
            <button className={button} disabled={busy||!draft.trim()} onClick={()=>{const spec=parse(draft);if(spec)request('propose_code_skill',{spec});}}>Save new candidate</button>
        </details>
        <p role="status">{notice}</p>
        <label className="block">Run inputs (JSON)<textarea className={input} value={values} onChange={e=>setValues(e.target.value)}/></label>
        {skills.map(skill=><article key={skill.id} className="rounded-lg border border-white/15 p-3 space-y-2">
            <h4 className="font-semibold">{skill.name} · {skill.status}</h4><p>{skill.description}</p>
            <details><summary>Review code, tests and provenance</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(skill,null,2)}</pre></details>
            <div className="flex flex-wrap gap-2">
                <button className={button} disabled={busy} onClick={()=>request('test_code_skill',{id:skill.id})}>Test examples</button>
                <button className={button} disabled={busy||skill.status!=='tested'} onClick={()=>{if(window.confirm(`Activate reviewed skill ${skill.name}? This replaces its active revision.`))request('activate_code_skill',{id:skill.id,approved:true});}}>Activate</button>
                <button className={button} disabled={busy||skill.status!=='active'} onClick={()=>{const inputs=parse(values);if(inputs!==undefined)request('run_code_skill',{id:skill.id,inputs});}}>Run skill</button>
                <button className={button} disabled={busy||skill.status!=='active'} onClick={()=>request('deactivate_code_skill',{id:skill.id})}>Deactivate</button>
                <button className={button} disabled={busy} onClick={()=>setDraft(JSON.stringify({name:skill.name,description:skill.description,source:skill.source,tests:skill.tests},null,2))}>Revise</button>
            </div>
        </article>)}
        {result&&<pre className="max-h-80 overflow-auto whitespace-pre-wrap text-xs" aria-label="Code skill result">{JSON.stringify(result,null,2)}</pre>}
        <p className="text-xs text-slate-400">Passing generated examples proves those examples only. Add your own expected results before activation. To roll back, test and activate the previous saved revision.</p>
    </section>;
}
