import React, {useEffect, useRef, useState} from 'react';

const IntelligenceConsole = React.lazy(() => import('./IntelligenceConsole'));

const button = 'rounded-lg border border-cyan-500/40 bg-cyan-950/40 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-900/50 disabled:opacity-40';
const input = 'w-full rounded-lg border border-white/20 bg-slate-950 p-2 text-sm text-slate-100';
const card = 'rounded-xl border border-cyan-500/20 bg-slate-950/70 p-4 space-y-3';

const PAGES = ['Jarvis Command Center', 'Autonomous Missions', 'Capabilities & Skills', 'Self-Upgrade Studio',
    'Repository Intelligence', 'Memory & Knowledge', 'Windows PC Manager', 'System Health',
    'Security & Approvals', 'Upgrade History'];

function Details({value, label = 'Inspect full result'}) {
    return <details className="text-sm"><summary className="cursor-pointer text-cyan-200">{label}</summary>
        <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-300">{JSON.stringify(value, null, 2)}</pre></details>;
}

function CandidateCard({candidate, repairs, busy, onTest, onActivate}) {
    const changes = Array.isArray(candidate.changes) ? candidate.changes : [];
    const provenance = candidate.provenance || null;
    const applied = repairs.some(repair => repair.id === candidate.repair_id && repair.status === 'applied');
    return <article className="space-y-2 rounded-lg border border-white/20 p-3">
        <div className="flex flex-wrap justify-between gap-2"><strong className="text-cyan-200">{candidate.id}</strong>
            <span className="text-xs text-slate-300">Upgrade status: {candidate.status}{candidate.repair_id ? ` · repair ${candidate.repair_id}` : ''}</span></div>
        <p className="text-sm break-words">Requested capability: <span className="text-slate-200">{(provenance && (provenance.goal || provenance.opportunity?.title)) || 'Not recorded; it was staged from a source repair request.'}</span></p>
        <p className="text-sm break-words">Source repositories: <span className="text-slate-200">{(provenance && provenance.repository) || 'Local Spark sources only'}</span></p>
        <p className="text-sm break-words">Files changed ({changes.length}): <span className="text-slate-200 break-all">{changes.map(c => c.path).join(', ') || 'None recorded'}</span></p>
        <p className="text-sm break-words">Risk classification: <span className="text-slate-200">{provenance ? 'Originated from a repository analysis; verify the diff manually before approval.' : 'Not machine-classified; inspect each replacement below.'}</span></p>
        <p className="text-sm break-words">Test results: <span className="text-slate-200">{candidate.status === 'staged' ? 'Not yet executed. Approval required.' : candidate.status === 'tested' ? 'Local regression tests passed.' : candidate.status === 'rejected' ? 'Tests failed; candidate rejected.' : candidate.status === 'activated' ? 'Applied after tests. Backups retained.' : 'Unknown.'}</span></p>
        <p className="text-sm break-words">Rollback availability: <span className="text-slate-200">{candidate.status === 'activated' ? (applied ? 'Journal and backups retained; use Upgrade History.' : 'Activation journal entry kept.') : 'Backups will be created on activation.'}</span></p>
        <div className="flex flex-wrap gap-2">
            {['staged', 'tested', 'rejected'].includes(candidate.status) && <button type="button" className={button} disabled={busy}
                onClick={() => onTest(candidate)}>Approve local tests</button>}
            {candidate.status === 'tested' && <button type="button" className={button} disabled={busy}
                onClick={() => onActivate(candidate)}>Approve activation</button>}
        </div>
        <Details value={candidate.changes} label="Inspect complete replacements"/>
    </article>;
}

export default function SparkScreens({socket, project, onCockpit}) {
    const [page, setPage] = useState('Jarvis Command Center');
    const [notice, setNotice] = useState(socket?.connected ? 'Ready. Every operation here stays read-only until you approve it.' : 'Backend offline. Connect and authenticate to SPARK.');
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);
    const [resultAction, setResultAction] = useState('');
    const [resultPage, setResultPage] = useState('');
    const [health, setHealth] = useState(null);
    const [diagnose, setDiagnose] = useState(null);
    const [registry, setRegistry] = useState(null);
    const [inventory, setInventory] = useState(null);
    const [roles, setRoles] = useState(null);
    const [skills, setSkills] = useState([]);
    const [candidates, setCandidates] = useState([]);
    const [repairs, setRepairs] = useState([]);
    const [analyses, setAnalyses] = useState([]);
    const [analysis, setAnalysis] = useState(null);
    const [evidence, setEvidence] = useState(null);
    const [filesReport, setFilesReport] = useState(null);
    const [filesHits, setFilesHits] = useState(null);
    const [forecast, setForecast] = useState(null);
    const [scan, setScan] = useState(null);
    const [profile, setProfile] = useState(null);
    const [agentJobs, setAgentJobs] = useState([]);

    const [repository, setRepository] = useState('');
    const [repoGoal, setRepoGoal] = useState('');
    const [referencePaths, setReferencePaths] = useState('');
    const [importUrl, setImportUrl] = useState('');
    const [paths, setPaths] = useState('backend/spark_task_planner.py');
    const [issue, setIssue] = useState('');
    const [lastIssue, setLastIssue] = useState('');
    const [pcDirectory, setPcDirectory] = useState('');
    const [largeMb, setLargeMb] = useState('');
    const [oldDays, setOldDays] = useState('');
    const [nearDup, setNearDup] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [freeGb, setFreeGb] = useState('');
    const [gbPerDay, setGbPerDay] = useState('');
    const [horizonDays, setHorizonDays] = useState('30');
    const [deepProbe, setDeepProbe] = useState(false);
    const [deepCheck, setDeepCheck] = useState(false);
    const [scanPaths, setScanPaths] = useState('backend/spark_task_planner.py');
    const [moduleName, setModuleName] = useState('');
    const [repeats, setRepeats] = useState('3');
    const [compareName, setCompareName] = useState('');
    const [compareBefore, setCompareBefore] = useState('');
    const [compareAfter, setCompareAfter] = useState('');

    const pending = useRef(null), deadline = useRef(null), serial = useRef(0), pageRef = useRef('');
    pageRef.current = page;

    function request(action, payload = {}, timeout = 120000) {
        if (!socket?.connected) {setNotice('Backend offline. Connect and authenticate to SPARK.'); return;}
        if (pending.current) {setNotice('Another operation is still running.'); return;}
        const id = `screens-${Date.now()}-${++serial.current}`;
        pending.current = id; setBusy(true); setNotice('Working…');
        clearTimeout(deadline.current);
        deadline.current = setTimeout(() => {pending.current = null; setBusy(false); setNotice('Request timed out. Refresh before retrying.');}, timeout);
        socket.emit('workspace_action', {workspace_token: socket.workspaceToken, request_id: id, action, project, payload});
    }

    useEffect(() => {
        pending.current = null; setBusy(false); setAnalysis(null); setEvidence(null);
        setNotice(socket?.connected ? 'Ready. Every operation here stays read-only until you approve it.' : 'Backend offline. Connect and authenticate to SPARK.');
        const listener = data => {
            if (!data || data.request_id !== pending.current) return;
            clearTimeout(deadline.current); pending.current = null; setBusy(false);
            if (!data.ok) {setNotice(data.message || 'Operation failed.'); return;}
            const r = data.result;
            setNotice(`${data.action.replaceAll('_', ' ')} completed.`);
            setResult(r); setResultAction(data.action); setResultPage(pageRef.current);
            switch (data.action) {
                case 'intelligence_health': setHealth(r); break;
                case 'self_heal_diagnose': setDiagnose(r); break;
                case 'saee_registry': setRegistry(r); break;
                case 'saee_inventory': setInventory(r); break;
                case 'workforce_roles': setRoles(r); break;
                case 'list_skills': setSkills(Array.isArray(r) ? r : []); break;
                case 'files_intelligence_scan': setFilesReport(r); break;
                case 'files_search': setFilesHits(r); break;
                case 'disk_forecast': setForecast(r); break;
                case 'profile_import_cost': case 'profile_compare': setProfile({...r, kind: data.action}); break;
                case 'security_scan': setScan(r); break;
                case 'import_repository': setEvidence(r); break;
                case 'analyze_repository': setAnalysis(r); break;
                case 'read_repository_analysis': setAnalysis(r); break;
                case 'list_repository_analyses': setAnalyses(Array.isArray(r) ? r : []); break;
                case 'list_repairs': setRepairs(Array.isArray(r) ? r : []); break;
                case 'list_repair_candidates': setCandidates(Array.isArray(r) ? r : []); break;
                case 'agent_snapshot': setAgentJobs((r && r.jobs) || []); break;
                case 'test_repair_candidate': case 'activate_repair_candidate': case 'stage_repository_upgrade': case 'heal_sources':
                    setCandidates(current => [r, ...current.filter(c => c && c.id !== r.id)]); break;
                case 'rollback_repair': setRepairs(current => current.map(item => item.id === r.id ? {...item, status: 'rolled_back'} : item)); break;
            }
        };
        const offline = () => {clearTimeout(deadline.current); pending.current = null; setBusy(false); setNotice('Backend offline. Refresh after reconnecting.');};
        socket.on('workspace_result', listener);
        socket.on('disconnect', offline);
        return () => {clearTimeout(deadline.current); socket.off('workspace_result', listener); socket.off('disconnect', offline);};
    }, [socket, project]);

    useEffect(() => {
        if (page !== 'Autonomous Missions' && page !== 'Memory & Knowledge') {setResult(null); setResultAction('');}
    }, [page, project]);

    function refresh(action, payload = {}, timeout) {
        pending.current = null; setBusy(false);
        request(action, payload, timeout);
    }

    const testCandidate = candidate => {
        if (window.confirm(`Run candidate ${candidate.id} in local regression tests? Staging is not an operating-system sandbox.`)) {refresh('test_repair_candidate', {id: candidate.id, approved: true}, 180000);}
    };
    const activateCandidate = candidate => {
        if (window.confirm(`Activate candidate ${candidate.id} in Spark? Backups are kept for rollback.`)) {refresh('activate_repair_candidate', {id: candidate.id, approved: true}, 180000);}
    };

    function runScan() {
        const entries = scanPaths.split(/\r?\n|,/).map(item => item.trim()).filter(Boolean);
        if (entries.length < 1 || entries.length > 16) {setNotice('Select one to sixteen backend paths for the scan.'); return;}
        request('security_scan', {paths: entries}, 180000);
    }

    function runFilesScan() {
        const payload = {directory: pcDirectory.trim()};
        if (largeMb.trim()) {const value = Number(largeMb); if (!Number.isFinite(value) || value < 1 || value > 100000) {setNotice('Large-file threshold must be between 1 and 100000 MB.'); return;} payload.large_mb = value;}
        if (oldDays.trim()) {const value = Number(oldDays); if (!Number.isFinite(value) || value < 1 || value > 3650) {setNotice('Age threshold must be between 1 and 3650 days.'); return;} payload.old_days = value;}
        if (nearDup) payload.near_dup = true;
        request('files_intelligence_scan', payload, 300000);
    }

    function runSearch() {
        if (!pcDirectory.trim() || !searchQuery.trim()) {setNotice('Enter a directory and a search phrase.'); return;}
        request('files_search', {directory: pcDirectory.trim(), query: searchQuery.trim()}, 300000);
    }

    function runForecast() {
        const free = Number(freeGb), rate = Number(gbPerDay), horizon = Number(horizonDays);
        if (!Number.isFinite(free) || !Number.isFinite(rate) || !Number.isFinite(horizon) || horizon < 1) {
            setNotice('Enter finite numbers; horizon must be at least one day.'); return;}
        request('disk_forecast', {free_gb: free, used_gb_per_day: rate, horizon_days: horizon}, 60000);
    }

    function runImportCost() {
        const count = Number(repeats);
        if (!moduleName.trim() || !Number.isInteger(count) || count < 1 || count > 10) {setNotice('Enter a module and a repeat count of 1-10.'); return;}
        request('profile_import_cost', {module: moduleName.trim(), repeats: count}, 300000);
    }

    function runCompare() {
        const before = Number(compareBefore), after = Number(compareAfter), tolerance = 0.1;
        if (!compareName.trim() || !Number.isFinite(before) || !Number.isFinite(after) || before < 0 || after < 0) {
            setNotice('Enter a benchmark name and non-negative numbers.'); return;}
        request('profile_compare', {name: compareName.trim(), before, after, tolerance}, 60000);
    }

    const showResult = result && resultPage === page;
    const awaitingApproval = agentJobs.filter(job => job.state === 'awaiting_approval').length;

    return <div className="mt-4 grid min-h-[28rem] gap-4 md:grid-cols-[11rem_minmax(0,1fr)]">
        <nav aria-label="Spark operating screens" className="flex flex-wrap content-start gap-2 md:flex-col">
            {PAGES.map(name => <button key={name} className={`${button} text-left ${page === name ? 'bg-cyan-900/70' : ''}`}
                aria-current={page === name ? 'page' : undefined} onClick={() => setPage(name)}>{name}</button>)}
        </nav>
        <main className="min-w-0 space-y-4">
            <div className="flex items-center justify-between"><h3 className="text-xl font-semibold text-cyan-100">{page}</h3>
                <span className="text-xs text-slate-400">Project: {project}</span></div>
            <p role="status" className="rounded-lg bg-cyan-950/40 p-3 text-sm text-cyan-100">{notice}</p>

            {page === 'Autonomous Missions' &&
                <React.Suspense fallback={<p role="status">Loading mission controls…</p>}>
                    <IntelligenceConsole socket={socket} project={project} initialPage="Agents"/></React.Suspense>}

            {page === 'Memory & Knowledge' &&
                <React.Suspense fallback={<p role="status">Loading memory controls…</p>}>
                    <IntelligenceConsole socket={socket} project={project} initialPage="Memory"/></React.Suspense>}

            {page === 'Jarvis Command Center' && <>
                <div className={card}>
                    <h4 className="font-semibold">Start here</h4>
                    <p className="text-sm text-slate-300">Ten operating screens for your locally owned SPARK: missions, skills,
                        upgrades, repositories, memory, the PC, system health, security and history. Approval gates carry over from the workspace.</p>
                    {onCockpit && <button type="button" className={button} onClick={onCockpit}>Open voice cockpit</button>}
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Live checks</h4>
                    <div className="flex flex-wrap gap-2">
                        <button type="button" className={button} disabled={busy} onClick={() => request('intelligence_health')}>Check core and interrupted jobs</button>
                        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={deepProbe} onChange={e => setDeepProbe(e.target.checked)}/>Deep (TCP probe)</label>
                        <button type="button" className={button} disabled={busy} onClick={() => request('self_heal_diagnose', {deep: deepProbe})}>Environmental check</button>
                    </div>
                    {health && <p className="text-sm text-slate-200">Spark core is {health.state}. {health.interrupted_jobs} interrupted workload(s) need review.</p>}
                    {diagnose && <p className="text-sm text-slate-200">Environment {diagnose.healthy ? 'healthy' : 'has findings'} — startup {diagnose.startup?.ok ? 'ok' : 'degraded'}, runtime {diagnose.runtime?.ok ? 'ok' : 'degraded'}, resources {diagnose.resources?.ok ? 'ok' : 'degraded'}.</p>}
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Go to a screen</h4>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {PAGES.filter(name => name !== 'Jarvis Command Center').map(name =>
                            <button key={name} type="button" onClick={() => setPage(name)}
                                className="rounded-xl border border-cyan-500/20 bg-slate-950/70 p-3 text-left text-cyan-100 hover:border-cyan-400">{name}</button>)}
                    </div>
                </div>
            </>}

            {page === 'Capabilities & Skills' && <>
                <div className={card}>
                    <h4 className="font-semibold">SAEE capability registry</h4>
                    <div className="flex flex-wrap gap-2">
                        <button type="button" className={button} disabled={busy} onClick={() => request('saee_registry')}>Declared capabilities and gaps</button>
                        <button type="button" className={button} disabled={busy} onClick={() => request('saee_inventory')}>Scan this checkout</button>
                    </div>
                    {registry && <>
                        <div className="max-h-64 overflow-auto text-xs">
                            {registry.capabilities.map(item => <div key={item.id} className="border-t border-white/10 py-2">
                                <strong className="text-cyan-200">{item.name}</strong>
                                <p className="text-slate-300">{item.summary}</p>
                                <p className="text-slate-500">Engine: {item.engine} · Gate: {item.gate} · {item.verified ? 'Verified inventory' : 'Declared'}</p>
                            </div>)}
                        </div>
                        <p className="text-sm text-amber-200">Known gaps: {registry.gaps.map(item => `${item.name} — ${item.summary}`).join('; ') || 'None recorded.'}</p>
                        <p className="text-xs text-slate-400">{registry.note}</p>
                    </>}
                    {inventory && <>
                        <p className="text-sm text-slate-200">Modules missing: {inventory.missing_modules.join(', ') || 'none'}. Capabilities without a naming test: {inventory.untested.join(', ') || 'none'}.</p>
                        <Details value={inventory.action_sets} label="Inspect exposed action sets"/>
                        <p className="text-xs text-slate-400">{inventory.note}</p>
                    </>}
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Specialist workforce roles</h4>
                    <button type="button" className={button} disabled={busy} onClick={() => request('workforce_roles')}>List roles</button>
                    {roles && <div className="max-h-64 overflow-auto text-xs">
                        {roles.map(role => <div key={role.id} className="border-t border-white/10 py-2">
                            <strong className="text-cyan-200">{role.name}</strong>
                            <p className="text-slate-300">{role.responsibility}</p>
                            <p className="break-all text-slate-500">Allowed actions: {role.actions.join(', ')}</p>
                        </div>)}
                    </div>}
                    <p className="text-xs text-slate-400">Assignments then route only through the approved evolution dispatcher with its own payload validation.</p>
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Calculation skills ({skills.length})</h4>
                    <button type="button" className={button} disabled={busy} onClick={() => request('list_skills')}>Refresh skill registry</button>
                    <div className="max-h-52 overflow-auto text-xs">
                        {skills.map(skill => <div key={skill.id} className="border-t border-white/10 py-2">
                            <strong className="text-cyan-200">{skill.name}</strong> — {skill.status}, rev {skill.revision || 1}: {skill.description}
                        </div>)}
                        {!skills.length && <p className="text-slate-400">No skills in this project yet.</p>}
                    </div>
                    <p className="text-xs text-slate-400">Create and activate skills in the Skill Forge tab.</p>
                </div>
            </>}

            {page === 'Self-Upgrade Studio' && <>
                <div className={card}>
                    <h4 className="font-semibold">Request a bounded source repair</h4>
                    <p className="text-sm text-slate-300">Uses the configured model on the selected files and issue. The candidate is staged, never applied. Repository-staged upgrades from Repository Intelligence also appear here.</p>
                    <textarea aria-label="Repair source paths" rows={3} className={input} value={paths}
                        onChange={e => setPaths(e.target.value)} placeholder="Backend Python paths, one per line or comma-separated (1-4)"/>
                    <textarea aria-label="Error to repair" rows={3} className={input} value={issue}
                        onChange={e => setIssue(e.target.value)} placeholder="Describe the error and expected behavior"/>
                    <button type="button" className={button} disabled={busy || !issue.trim()}
                        onClick={() => {setLastIssue(issue.trim()); refresh('heal_sources', {paths: paths.split(/\r?\n|,/).map(p => p.trim()).filter(Boolean), issue: issue.trim()}, 600000);}}>
                        Generate staged repair</button>
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Candidates ({candidates.length})</h4>
                    <div className="flex flex-wrap gap-2">
                        <button type="button" className={button} disabled={busy} onClick={() => refresh('list_repair_candidates')}>Refresh candidates</button>
                        <button type="button" className={button} disabled={busy} onClick={() => refresh('list_repairs')}>Refresh activation history</button>
                    </div>
                    {candidates.map(candidate => <CandidateCard key={candidate.id} candidate={candidate} repairs={repairs}
                        busy={busy} onTest={testCandidate} onActivate={activateCandidate}/>)}
                    {!candidates.length && <p className="text-sm text-slate-400">No candidates loaded.</p>}
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Measure import cost (resource impact)</h4>
                    <div className="flex flex-wrap gap-2">
                        <input aria-label="Python module" className={`${input} max-w-xs`} value={moduleName} onChange={e => setModuleName(e.target.value)} placeholder="e.g. json"/>
                        <input aria-label="Repeat count" className={`${input} max-w-24`} value={repeats} onChange={e => setRepeats(e.target.value)}/>
                        <button type="button" className={button} disabled={busy} onClick={runImportCost}>Measure fresh import</button>
                    </div>
                    {profile?.kind === 'profile_import_cost' && <p className="text-sm text-slate-200">Fresh import of {profile.module}: {profile.seconds} s (best of {profile.repeats}).</p>}
                    <p className="text-xs text-slate-400">Runs the real interpreter import in a fresh subprocess. Read-only measurement.</p>
                </div>
            </>}

            {page === 'Repository Intelligence' && <>
                <div className={card}>
                    <h4 className="font-semibold">Learn from a repository</h4>
                    <p className="text-sm text-slate-300">Accepts a local checkout path or an https GitHub URL (shallow, code-execution-free clone). Analysis sends a bounded source sample to the configured model.</p>
                    <input aria-label="Repository path or GitHub URL" className={input} value={repository} onChange={e => setRepository(e.target.value)} placeholder="Absolute local path or https://github.com/owner/repo"/>
                    <textarea aria-label="Repository upgrade goal" className={input} value={repoGoal} onChange={e => setRepoGoal(e.target.value)} placeholder="What should Spark learn or improve from this repository?"/>
                    <textarea aria-label="Reference paths" className={input} value={referencePaths} onChange={e => setReferencePaths(e.target.value)} placeholder="Optional reference paths, one per line"/>
                    <div className="flex flex-wrap gap-2">
                        <button type="button" className={button} disabled={busy || !repository.trim() || !repoGoal.trim()}
                            onClick={() => refresh('analyze_repository', {repository: repository.trim(), goal: repoGoal.trim(), reference_paths: referencePaths.split(/\r?\n/).map(p => p.trim()).filter(Boolean)}, 600000)}>
                            Analyze repository with model</button>
                        <button type="button" className={button} disabled={busy} onClick={() => refresh('list_repository_analyses')}>Load saved analyses</button>
                    </div>
                    {analyses.map(report => <button key={report.id} className={button} disabled={busy}
                        onClick={() => refresh('read_repository_analysis', {id: report.id})}>{`${report.goal}`.slice(0, 80)}</button>)}
                    {analysis && <>
                        <p className="break-all text-sm">{analysis.repository}</p>
                        <p className="whitespace-pre-wrap text-sm">{analysis.summary}</p>
                        <Details value={{sources: analysis.sources, skipped: analysis.skipped}} label="Inspect sampled source and coverage"/>
                        {analysis.opportunities.map((item, index) => <div key={index} className="space-y-1 rounded-lg border border-white/20 p-3 text-sm">
                            <strong>{item.title}</strong>
                            <p className="text-slate-300">{item.rationale}</p>
                            <p className="text-xs text-slate-400">Evidence: {item.evidence.join(', ')}</p>
                            <button type="button" className={button} disabled={busy}
                                onClick={() => refresh('stage_repository_upgrade', {analysis_id: analysis.id, opportunity: index}, 600000)}>
                                Generate staged Spark upgrade</button>
                        </div>)}
                        {!analysis.opportunities.length && <p className="text-sm text-slate-400">No supported upgrade in this sample.</p>}
                    </>}
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Import GitHub evidence only (no model call)</h4>
                    <div className="flex flex-wrap gap-2">
                        <input aria-label="GitHub URL" className={`${input} max-w-md`} value={importUrl} onChange={e => setImportUrl(e.target.value)} placeholder="https://github.com/owner/repo"/>
                        <button type="button" className={button} disabled={busy || !importUrl.trim()}
                            onClick={() => refresh('import_repository', {url: importUrl.trim(), reference_paths: referencePaths.split(/\r?\n/).map(p => p.trim()).filter(Boolean)}, 600000)}>
                            Import license and dependency evidence</button>
                    </div>
                    {evidence && <>
                        <p className="text-sm break-words">Repository: {evidence.repository}</p>
                        <p className="text-sm text-slate-200">License: {evidence.license?.spdx || 'none found'} ({evidence.license?.class}) — {evidence.license?.note}</p>
                        <Details value={evidence.dependency_map} label="Inspect dependency manifests"/>
                        <Details value={{imported: evidence.imported, limitations: evidence.limitations}} label="Inspect import chain of custody"/>
                    </>}
                </div>
            </>}

            {page === 'Windows PC Manager' && <>
                <div className={card}>
                    <h4 className="font-semibold">LOCAL APPS — read-only PC scan</h4>
                    <p className="text-sm text-slate-300">Scans a real directory: large files, stale files, exact duplicates, near-duplicate text documents, redundant installers and duplicate downloads. Nothing is moved or deleted.</p>
                    <input aria-label="Directory to scan" className={input} value={pcDirectory} onChange={e => setPcDirectory(e.target.value)} placeholder="Absolute Windows directory, e.g. C:\Users\name\Downloads"/>
                    <div className="flex flex-wrap items-center gap-2">
                        <input aria-label="Large file threshold in MB" className={`${input} max-w-40`} value={largeMb} onChange={e => setLargeMb(e.target.value)} placeholder="Large file MB (optional)"/>
                        <input aria-label="Old file threshold in days" className={`${input} max-w-40`} value={oldDays} onChange={e => setOldDays(e.target.value)} placeholder="Older than days (optional)"/>
                        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={nearDup} onChange={e => setNearDup(e.target.checked)}/>Near-duplicate documents</label>
                        <button type="button" className={button} disabled={busy || !pcDirectory.trim()} onClick={runFilesScan}>Run PC scan</button>
                    </div>
                    {filesReport && <>
                        <p className="text-sm text-slate-200">{filesReport.file_count} files scanned{filesReport.truncated ? ' (listing truncated)' : ''}. Reclaimable from duplicate/temp files: {(filesReport.reclaimable_bytes / 1073741824).toFixed(2)} GB.</p>
                        <p className="text-xs text-slate-300">Exact duplicates: {filesReport.duplicates?.length}. Near-duplicates: {filesReport.near_duplicates?.length}. Redundant installers: {filesReport.redundant_installers?.length}. Duplicate downloads: {filesReport.duplicate_downloads?.length}.</p>
                        <ul className="text-xs text-slate-300 text-wrap list-disc pl-5">{(filesReport.recommendations || []).map((item, index) => <li key={index}>{item}</li>)}</ul>
                        <Details value={filesReport} label="Inspect the complete PC report"/>
                        <p className="text-xs text-slate-400">{filesReport.note}</p>
                    </>}
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Find files in plain language</h4>
                    <div className="flex flex-wrap gap-2">
                        <input aria-label="Directory to search" className={`${input} max-w-md`} value={pcDirectory} onChange={e => setPcDirectory(e.target.value)}/>
                        <input aria-label="Natural language file query" className={`${input} max-w-md`} value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                            placeholder="e.g. pdf larger than 50 mb older than 1 month" onKeyDown={e => {if (e.key === 'Enter') runSearch();}}/>
                        <button type="button" className={button} disabled={busy || !searchQuery.trim() || !pcDirectory.trim()} onClick={runSearch}>Search</button>
                    </div>
                    {filesHits && <>
                        <p className="text-sm text-slate-200">{filesHits.file_count} files scanned; {filesHits.results?.length} match(es){filesHits.truncated ? ' (listing truncated)' : ''}.</p>
                        <div className="max-h-64 overflow-auto text-xs">
                            {filesHits.results?.map(hit => <div key={hit.path} className="border-t border-white/10 py-1 break-all">
                                {hit.path} <span className="text-slate-500">({(hit.size / 1048576).toFixed(2)} MB, score {hit.score})</span>
                            </div>)}
                        </div>
                        <Details value={filesHits.intent} label="Inspect parsed search intent"/>
                        <p className="text-xs text-slate-400">{filesHits.note}</p>
                    </>}
                </div>
            </>}

            {page === 'System Health' && <>
                <div className={card}>
                    <h4 className="font-semibold">Environmental diagnosis</h4>
                    <div className="flex flex-wrap items-center gap-2">
                        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={deepCheck} onChange={e => setDeepCheck(e.target.checked)}/>Deep (TCP connectivity probe)</label>
                        <button type="button" className={button} disabled={busy} onClick={() => request('self_heal_diagnose', {deep: deepCheck})}>Diagnose environment</button>
                    </div>
                    {diagnose && <>
                        <p className="text-sm text-slate-200">{diagnose.healthy ? 'All required checks pass.' : 'Findings reported — review the sections below.'}</p>
                        <Details value={diagnose} label="Inspect startup, dependencies, runtime, resources and connectivity"/>
                    </>}
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Crash recovery</h4>
                    <p className="text-sm text-slate-300">Restores repair backups for interrupted changes after a crash, with integrity checks. Runs under the existing maintenance gate.</p>
                    <button type="button" className={button} disabled={busy}
                        onClick={() => {if (window.confirm('Recover interrupted repair backups now? Failed restorations stay quarantined.')) refresh('self_heal_recover');}}>
                        Approve crash recovery</button>
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Disk space forecast</h4>
                    <div className="flex flex-wrap gap-2">
                        <input aria-label="Free disk space in GB" className={`${input} max-w-40`} value={freeGb} onChange={e => setFreeGb(e.target.value)} placeholder="Free GB"/>
                        <input aria-label="Growth per day in GB" className={`${input} max-w-40`} value={gbPerDay} onChange={e => setGbPerDay(e.target.value)} placeholder="Growth GB/day"/>
                        <input aria-label="Forecast horizon in days" className={`${input} max-w-40`} value={horizonDays} onChange={e => setHorizonDays(e.target.value)}/>
                        <button type="button" className={button} disabled={busy} onClick={runForecast}>Forecast</button>
                    </div>
                    {forecast && <p className="text-sm text-slate-200">Projected free space in {forecast.horizon_days} days: {forecast.projected_free_gb} GB{forecast.days_to_empty != null ? `; empty in about ${forecast.days_to_empty} days` : ''}{forecast.warning ? ' — warning threshold reached.' : '.'}</p>}
                </div>
            </>}

            {page === 'Security & Approvals' && <>
                <div className={card}>
                    <h4 className="font-semibold">Secret and static code scan (read-only)</h4>
                    <textarea aria-label="Backend paths to scan" rows={3} className={input} value={scanPaths} onChange={e => setScanPaths(e.target.value)}
                        placeholder="One backend Python path per line (1-16)"/>
                    <button type="button" className={button} disabled={busy} onClick={runScan}>Scan selected sources</button>
                    {scan && <>
                        <p className="text-sm text-slate-200">{scan.secret_count} secret finding(s), {scan.blocked} action-blocking issue(s). Signature: {scan.signature}.</p>
                        <ul className="max-h-48 overflow-auto text-xs list-disc pl-5 text-slate-300">
                            {scan.findings?.map((finding, index) => <li key={index}>{finding.path}: {finding.kind}{finding.detail ? ` — ${finding.detail}` : ''}</li>)}
                            {!scan.findings?.length && <li>No findings recorded.</li>}
                        </ul>
                        <Details value={scan} label="Inspect the raw scan result"/>
                    </>}
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Approval queue</h4>
                    <div className="flex flex-wrap gap-2">
                        <button type="button" className={button} disabled={busy} onClick={() => refresh('list_repair_candidates')}>
                            Pending upgrades ({candidates.filter(c => c.status === 'staged').length})</button>
                        <button type="button" className={button} disabled={busy} onClick={() => refresh('agent_snapshot')}>Refresh agent workloads</button>
                    </div>
                    <p className="text-sm text-slate-200">{candidateCountLabel(candidates)} · Agent plans awaiting approval: {agentJobs.length ? awaitingApproval : 'not loaded'}.</p>
                    <p className="text-xs text-slate-400">Agent plan approvals happen in Autonomous Missions with the exact plan hash. Upgrade approvals need local tests first.</p>
                    {candidates.map(candidate => <CandidateCard key={candidate.id} candidate={candidate} repairs={repairs}
                        busy={busy} onTest={testCandidate} onActivate={activateCandidate}/>)}
                </div>
            </>}

            {page === 'Upgrade History' && <>
                <div className={card}>
                    <h4 className="font-semibold">Repairs and upgrades with rollback</h4>
                    <button type="button" className={button} disabled={busy} onClick={() => refresh('list_repairs')}>Refresh history</button>
                    {repairs.map(repair => <article key={repair.id} className="space-y-2 rounded-lg border border-white/20 p-3 text-sm">
                        <div className="flex flex-wrap justify-between gap-2"><strong className="text-cyan-200">{repair.id}</strong>
                            <span className={"text-xs " + (repair.status === 'applied' ? 'text-emerald-300' : 'text-slate-300')}>{repair.status}</span></div>
                        <p className="break-all text-xs text-slate-400">Files: {repair.files?.map(entry => entry.path).join(', ')}</p>
                        {repair.status === 'applied' && <button type="button" className={button} disabled={busy}
                            onClick={() => {if (window.confirm(`Roll back repair ${repair.id}? Preserves any later human edits.`)) refresh('rollback_repair', {id: repair.id});}}>Roll back</button>}
                    </article>)}
                    {!repairs.length && <p className="text-sm text-slate-400">No activation history loaded.</p>}
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Before/after benchmark</h4>
                    <div className="flex flex-wrap gap-2">
                        <input aria-label="Benchmark name" className={`${input} max-w-xs`} value={compareName} onChange={e => setCompareName(e.target.value)} placeholder="e.g. import-cost-json"/>
                        <input aria-label="Before value" className={`${input} max-w-32`} value={compareBefore} onChange={e => setCompareBefore(e.target.value)} placeholder="Before"/>
                        <input aria-label="After value" className={`${input} max-w-32`} value={compareAfter} onChange={e => setCompareAfter(e.target.value)} placeholder="After"/>
                        <button type="button" className={button} disabled={busy} onClick={runCompare}>Compare (10% tolerance)</button>
                    </div>
                    {profile?.kind === 'profile_compare' && <p className="text-sm text-slate-200">{profile.name}: {profile.verdict.replace(/_/g, ' ')} (delta {profile.delta}, {profile.relative} relative). {profile.recommendation}</p>}
                    <p className="text-xs text-slate-400">Lower values are treated as better. Sub-tolerance differences never count as improvements.</p>
                </div>
                <div className={card}>
                    <h4 className="font-semibold">Candidates snapshot</h4>
                    <button type="button" className={button} disabled={busy} onClick={() => refresh('list_repair_candidates')}>Refresh candidates</button>
                    {candidates.map(candidate => <CandidateCard key={candidate.id} candidate={candidate} repairs={repairs}
                        busy={busy} onTest={testCandidate} onActivate={activateCandidate}/>)}
                </div>
            </>}

            {showResult && <div className={card}><Details value={result} label={`${resultAction} — latest response`}/></div>}
        </main>
    </div>;
}

function candidateCountLabel(candidates) {
    const staged = candidates.filter(c => c.status === 'staged').length;
    const tested = candidates.filter(c => c.status === 'tested').length;
    if (!candidates.length) return 'No upgrade candidates loaded.';
    return `Upgrade candidates: ${staged} staged, ${tested} tested, ${candidates.length - staged - tested} other.`;
}
