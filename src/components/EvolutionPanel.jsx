import ReaWorkflowPanel from './ReaWorkflowPanel';
import React, {useEffect, useRef, useState} from 'react';

const button = 'rounded-lg border border-cyan-600/50 bg-cyan-950/50 px-3 py-2 text-sm text-cyan-100 disabled:opacity-40';
const input = 'w-full rounded-lg border border-white/20 bg-slate-900 p-2 text-sm';

export default function EvolutionPanel({socket, project}) {
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState('Ready. Select an operation.');
    const [description, setDescription] = useState('');
    const [baseId, setBaseId] = useState('');
    const [paths, setPaths] = useState('backend/spark_task_planner.py');
    const [issue, setIssue] = useState('');
    const [repairs, setRepairs] = useState([]);
    const [candidates, setCandidates] = useState([]);
    const [tools, setTools] = useState([]);
    const [autonomy, setAutonomy] = useState(null);
    const [upgradeGoal, setUpgradeGoal] = useState("");
    const [toolName, setToolName] = useState('');
    const [argumentsText, setArgumentsText] = useState('{}');
    const [repository, setRepository] = useState('');
    const [repoGoal, setRepoGoal] = useState('');
    const [referencePaths, setReferencePaths] = useState('');
    const [analysis, setAnalysis] = useState(null);
    const [analyses, setAnalyses] = useState([]);
    const pending = useRef(null);
    const deadline = useRef(null);
    const serial = useRef(0);

    useEffect(() => {
        pending.current = null;
        setBusy(false);
        setAnalysis(null);
        setAnalyses([]);
        setCandidates([]);
        setRepairs([]);
        setResult('Ready. Select an operation.');
        const listener = data => {
            if (data?.action==='saee_autonomy_stop' && String(data.request_id).startsWith('emergency-stop-')) {
                setResult(data.ok?'Autonomous evolution stopped. In-flight work cannot activate additional changes.':String(data.message||'Emergency stop failed.'));
                if(data.ok)setAutonomy(data.result);
                return;
            }
            if (data?.request_id !== pending.current) return;
            clearTimeout(deadline.current);
            pending.current = null;
            setBusy(false);
            setResult(data.ok ? JSON.stringify(data.result, null, 2) : String(data.message));
            if (data.ok && ['saee_autonomy_status','saee_autonomy_configure','saee_autonomy_stop','saee_autonomy_goal','saee_autonomy_cancel_goal'].includes(data.action)) setAutonomy(data.result);
            if (data.ok && data.action === 'saee_autonomy_cycle') setAutonomy(current => current ? {...current,last_status:data.result?.status} : current);
            if (data.ok && data.action === 'rea_discover') {
                setTools(data.result);
                setToolName(data.result[0]?.name || '');
            }
            if (data.ok && data.action === 'list_repairs') setRepairs(data.result);
            if (data.ok && data.action === 'list_repair_candidates') setCandidates(data.result);
            if (data.ok && ['analyze_repository', 'read_repository_analysis'].includes(data.action)) setAnalysis(data.result);
            if (data.ok && data.action === 'list_repository_analyses') setAnalyses(data.result);
            if (data.ok && ['stage_repository_upgrade', 'heal_sources', 'test_repair_candidate'].includes(data.action)) {
                setCandidates(current => [data.result, ...current.filter(c => c.id !== data.result.id)]);
            }
            if (data.ok && data.action === 'activate_repair_candidate') {
                setCandidates([]);
                setRepairs(current => [data.result, ...current.filter(r => r.id !== data.result.id)]);
            }
            if (data.ok && data.action === 'rollback_repair') {
                setRepairs(current => current.map(r => r.id === data.result.id ? {...r, status: 'rolled_back'} : r));
            }
        };
        const disconnect = () => {clearTimeout(deadline.current); pending.current = null; setBusy(false); setResult('Backend disconnected. Check repair history after reconnecting.');};
        socket.on('workspace_result', listener);
        socket.on('disconnect', disconnect);
        return () => {clearTimeout(deadline.current); socket.off('workspace_result', listener); socket.off('disconnect', disconnect);};
    }, [socket, project]);

    function request(action, payload = {}) {
        if (busy || pending.current) return;
        if (!socket.connected) {setResult('Connect SPARK first.'); return;}
        pending.current = `evolution-${Date.now()}-${++serial.current}`;
        setBusy(true);
        setResult('Working…');
        clearTimeout(deadline.current);
        deadline.current = setTimeout(() => {
            pending.current = null;
            setBusy(false);
            setResult('Request timed out. It may still be finishing on the backend. Check backups before retrying a repair.');
        }, 240000);
        socket.emit('workspace_action', {workspace_token:socket.workspaceToken,request_id: pending.current, action, project, payload});
    }

    function emergencyStop() {
        if (!socket.connected) {setResult('Cannot reach SPARK backend to stop autonomy. Stop the backend to halt operations.'); return;}
        socket.emit('workspace_action',{
            workspace_token:socket.workspaceToken, request_id:'emergency-stop-'+Date.now(),
            action:'saee_autonomy_stop',project,payload:{}
        });
    }
    const selected = tools.find(tool => tool.name === toolName);
    return <div className="mt-3 grid gap-4 lg:grid-cols-2">
        <ReaWorkflowPanel socket={socket} project={project}/>
        <section aria-label="Autonomous self-evolution" className="space-y-3 rounded-xl border border-cyan-500/20 p-4 lg:col-span-2">
            <h3 className="text-lg font-semibold">Self-Evolution and REA</h3>
            <p className="text-sm text-slate-300">SPARK can inspect its own backend, check REA availability and repair eligible Python syntax errors on its own. Upgrade frequency follows the persisted policy; zero daily cap allows successive success-gated upgrades. Every code repair runs staged and live checks and retains a rollback journal. It never runs unknown REA tools automatically.</p>
            <div className="flex flex-wrap gap-2">
                <button type="button" className={button} disabled={busy} onClick={()=>request('saee_autonomy_status')}>Check autonomy status</button>
                <button type="button" className={button} disabled={busy} onClick={()=>request('saee_autonomy_configure',{enabled:true,allow_model_source:false})}>Enable hourly checks</button>
                <button type="button" className={button} disabled={busy} onClick={()=>{
                    if(window.confirm('Permit SPARK to send bounded backend Python source to the configured model, then automatically test and activate eligible syntax repairs? Validation runs local code and is NOT an operating-system sandbox.'))
                        request('saee_autonomy_configure',{enabled:true,allow_model_source:true});
                }}>Enable autonomous repairs</button>
                <button type="button" className={button} disabled={busy} onClick={()=>request('saee_autonomy_cycle')}>Run inspection now</button>
                <button type="button" className={button+' border-red-400/60 text-red-200'} disabled={!socket.connected} onClick={emergencyStop}>Emergency stop</button>
            </div>
            <label className="block text-sm text-slate-200">Autonomous upgrade goal
                <textarea aria-label="Autonomous upgrade goal" className={input} value={upgradeGoal}
                    onChange={e=>setUpgradeGoal(e.target.value)}
                    placeholder="Example: Improve spark_task_planner reliability while preserving existing behavior" />
            </label>
            <div className="flex flex-wrap gap-2">
                <button type="button" className={button} disabled={busy || upgradeGoal.trim().length<10}
                    onClick={()=>request('saee_autonomy_goal',{goal:upgradeGoal.trim()})}>Queue upgrade</button>
                <button type="button" className={button} disabled={busy} onClick={()=>request('saee_autonomy_cancel_goal')}>Cancel queued upgrade</button>
                {autonomy?.queued_goal&&<span className="text-sm text-cyan-200">Queued: {autonomy.queued_goal}</span>}
            </div>
            <p className="text-sm text-slate-300" role="status">Autonomy: {autonomy ? (autonomy.enabled?'Enabled':'Off')+' · '+(autonomy.allow_model_source?'Model-assisted repairs allowed':'No source sharing')+' · Last: '+autonomy.last_status : 'Status not checked'}.</p>
            <details className="text-xs text-slate-400"><summary>Safety boundaries</summary>
                Existing non-protected Python sources only; no new dependencies, new files, authentication changes, shell instructions, unrelated PC operations or arbitrary REA tool execution. The installed MCP catalog is inspected read-only. The standing grant stays on this PC and can be revoked with Emergency stop.
            </details>
        </section>
        <div className="space-y-3 rounded-xl border border-cyan-500/20 p-3 lg:col-span-2">
            <h3 className="font-semibold">Learn from a repository</h3>
            <p className="text-sm text-slate-300">Choose a local source checkout and describe an improvement to Spark. Analysis sends a bounded source sample to your configured Groq model. It returns source references and upgrade suggestions. Clone remote repositories locally first. Repository code is read, never executed during analysis.</p>
            <input aria-label="Repository directory" className={input} value={repository} onChange={e => setRepository(e.target.value)} placeholder="Absolute local repository path" />
            <textarea aria-label="Repository upgrade goal" className={input} value={repoGoal} onChange={e => setRepoGoal(e.target.value)} placeholder="What should Spark learn or improve from this repository?" />
            <textarea aria-label="Repository reference paths" className={input} value={referencePaths} onChange={e => setReferencePaths(e.target.value)} placeholder="Optional reference paths, one per line. Blank selects a sample of README, manifests and source files." />
            <p className="text-xs text-slate-400">Up to 16 UTF-8 files, 64 KiB each and 192 KiB total. Hidden files and sensitive filenames are excluded. Review which source files you share with the model. Findings describe sampled source; runtime behavior remains unverified.</p>
            <div className="flex flex-wrap gap-2">
                <button className={button} disabled={busy || !repository.trim() || !repoGoal.trim()} onClick={() => request('analyze_repository', {repository: repository.trim(), goal: repoGoal.trim(), reference_paths: referencePaths.split(/\r?\n/).map(p => p.trim()).filter(Boolean)})}>Analyze repository with model</button>
                <button className={button} disabled={busy} onClick={() => request('list_repository_analyses')}>Load saved analyses</button>
            </div>
            {analyses.map(report => <button key={report.id} className={`${button} mr-2`} disabled={busy} onClick={() => request('read_repository_analysis', {id: report.id})}>{report.goal}</button>)}
            {analysis && <div className="space-y-3 text-sm">
                <p className="break-all">{analysis.repository}</p>
                <p className="whitespace-pre-wrap">{analysis.summary}</p>
                <details><summary>Inspect sampled source and coverage</summary><pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify({sources: analysis.sources, skipped: analysis.skipped, inventory_truncated: analysis.inventory_truncated, limitations: analysis.limitations}, null, 2)}</pre></details>
                {!analysis.opportunities.length && <p>No supported upgrade was identified in this sample. Try a more specific goal or select different reference files.</p>}
                {analysis.opportunities.map((item, index) => <div key={index} className="space-y-2 rounded-lg border border-white/20 p-3">
                    <h4 className="font-semibold">{item.title}</h4>
                    <p>{item.rationale}</p>
                    <p className="break-words">Source evidence: {item.evidence.join(', ')}</p>
                    <p className="break-words">Spark files: {item.spark_paths.join(', ')}</p>
                    <p>Acceptance check: {item.verification}</p>
                    <button className={button} disabled={busy} onClick={() => request('stage_repository_upgrade', {analysis_id: analysis.id, opportunity: index})}>Generate staged Spark upgrade</button>
                </div>)}
                <p>Generated upgrades appear below for inspection, approved local tests and separate activation. Existing backend Python files are supported. Recovery and authorization modules require manual upgrades.</p>
            </div>}
        </div>
        <div className="space-y-3 rounded-xl border border-cyan-500/20 p-3">
            <h3 className="font-semibold">Generate and upgrade skills</h3>
            <p className="text-sm text-slate-300">Describe a calculation. Spark stages a declarative skill and tests its examples. Review and activate the tested candidate in Skill Forge. Failed upgrades preserve the active revision.</p>
            <textarea aria-label="Requested skill" className={input} value={description} onChange={e => setDescription(e.target.value)} placeholder="Calculate a percentage of an amount" />
            <input aria-label="Base skill revision ID" className={input} value={baseId} onChange={e => setBaseId(e.target.value)} placeholder="Active revision ID to upgrade, or leave blank for a new skill" />
            <button className={button} disabled={busy || !description.trim()} onClick={() => request('generate_skill', {description, base_id: baseId.trim() || null})}>Generate and test candidate</button>
            <h3 className="font-semibold pt-3">Source self-healing</h3>
            <p className="text-sm text-slate-300">Generation sends selected source files and the issue to your configured Groq model. Requires GROQ_API_KEY. Review the staged replacement before approving local test execution. Activation requires separate approval and repeats verification. Failed activation rolls back.</p>
            <input aria-label="Repair source paths" className={input} value={paths} onChange={e => setPaths(e.target.value)} placeholder="Comma-separated backend Python paths" />
            <textarea aria-label="Error to repair" className={input} value={issue} onChange={e => setIssue(e.target.value)} placeholder="Describe the error and expected behavior" />
            <div className="flex flex-wrap gap-2">
                <button className={button} disabled={busy} onClick={() => request('diagnose_sources')}>Detect errors</button>
                <button className={button} disabled={busy || !issue.trim()} onClick={() => request('heal_sources', {paths: paths.split(',').map(p => p.trim()).filter(Boolean), issue})}>Generate staged repair</button>
                <button className={button} disabled={busy} onClick={() => request('list_repair_candidates')}>Review candidates</button>
                <button className={button} disabled={busy} onClick={() => request('list_repairs')}>Refresh backups</button>
            </div>
            {candidates.map(candidate=><div key={candidate.id} className="space-y-2 rounded-lg border border-white/20 p-2 text-sm">
                <p>{candidate.id}: {candidate.status}</p>
                {candidate.provenance && <details><summary>Repository evidence and acceptance check</summary><pre className="max-h-52 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(candidate.provenance,null,2)}</pre></details>}
                <details><summary>Inspect complete replacements</summary><pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(candidate.changes,null,2)}</pre></details>
                {['staged','tested','rejected'].includes(candidate.status)&&<button className={button} disabled={busy} onClick={()=>{if(window.confirm('Run the inspected candidate code in local regression tests? Staging is a temporary directory, not an operating-system security sandbox.'))request('test_repair_candidate',{id:candidate.id,approved:true});}}>Approve local tests</button>}
                {candidate.status==='tested'&&<button className={button} disabled={busy} onClick={()=>{if(window.confirm('Activate this inspected, tested source replacement in Spark? Backups are kept for rollback.'))request('activate_repair_candidate',{id:candidate.id,approved:true});}}>Approve activation</button>}
            </div>)}
            {repairs.map(repair => <div className="text-sm break-all" key={repair.id}>
                {repair.id}: {repair.status}
                {repair.status === 'applied' && <button className={button} disabled={busy} onClick={() => request('rollback_repair', {id: repair.id})}>Roll back</button>}
            </div>)}
        </div>
        <div className="space-y-3 rounded-xl border border-cyan-500/20 p-3">
            <h3 className="font-semibold">Direct REA tools</h3>
            <p className="text-sm text-slate-300">Discover the installed REA MCP catalog and call any tool directly. The connection retains active-target state. Tool availability depends on your installed analysis engines.</p>
            <button className={button} disabled={busy} onClick={() => request('rea_discover')}>Discover REA tools</button>
            <select aria-label="REA tool" className={input} value={toolName} onChange={e => setToolName(e.target.value)}>
                <option value="">Select tool</option>
                {tools.map(tool => <option key={tool.name} value={tool.name}>{tool.name}</option>)}
            </select>
            <p className="text-sm text-slate-300 whitespace-pre-wrap">{selected?.description}</p>
            {selected && <details><summary className="cursor-pointer text-sm">Argument schema</summary><pre className="max-h-52 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(selected.inputSchema, null, 2)}</pre></details>}
            <textarea aria-label="REA arguments JSON" className={`${input} font-mono`} rows={5} value={argumentsText} onChange={e => setArgumentsText(e.target.value)} />
            <button className={button} disabled={busy || !selected} onClick={() => {
                try {
                    const args = JSON.parse(argumentsText);
                    if (window.confirm(`Run REA tool ${toolName} with these arguments? This tool may inspect or modify local targets.\n${argumentsText}`)) request('rea_call', {name: toolName, arguments: args});
                } catch {setResult('Enter valid JSON arguments.');}
            }}>Run selected REA tool</button>
            <pre role="status" aria-live="polite" className="max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-black/50 p-3 text-xs">{result}</pre>
        </div>
    </div>;
}
