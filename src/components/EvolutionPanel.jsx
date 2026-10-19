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
    const [toolName, setToolName] = useState('');
    const [argumentsText, setArgumentsText] = useState('{}');
    const pending = useRef(null);
    const deadline = useRef(null);
    const serial = useRef(0);

    useEffect(() => {
        pending.current = null;
        setBusy(false);
        setResult('Ready. Select an operation.');
        const listener = data => {
            if (data?.request_id !== pending.current) return;
            clearTimeout(deadline.current);
            pending.current = null;
            setBusy(false);
            setResult(data.ok ? JSON.stringify(data.result, null, 2) : String(data.message));
            if (data.ok && data.action === 'rea_discover') {
                setTools(data.result);
                setToolName(data.result[0]?.name || '');
            }
            if (data.ok && data.action === 'list_repairs') setRepairs(data.result);
            if (data.ok && data.action === 'list_repair_candidates') setCandidates(data.result);
        };
        const disconnect = () => {clearTimeout(deadline.current); pending.current = null; setBusy(false); setResult('Backend disconnected. Check repair history after reconnecting.');};
        socket.on('workspace_result', listener);
        socket.on('disconnect', disconnect);
        return () => {clearTimeout(deadline.current); socket.off('workspace_result', listener); socket.off('disconnect', disconnect);};
    }, [socket, project]);

    function request(action, payload = {}) {
        if (busy) return;
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

    const selected = tools.find(tool => tool.name === toolName);
    return <div className="mt-3 grid gap-4 lg:grid-cols-2">
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
