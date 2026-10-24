import React, {useEffect, useMemo, useRef, useState} from 'react';

const buttonStyle = 'rounded-lg border border-cyan-600/50 bg-cyan-950/50 px-3 py-2 text-sm font-semibold text-cyan-100 hover:bg-cyan-800/60 disabled:opacity-40';
const panelStyle = 'rounded-xl border border-cyan-500/20 bg-black/40 p-3';
const inputStyle = 'rounded-md border border-cyan-500/30 bg-slate-950/70 px-2 py-1 text-sm text-cyan-100 w-full';

function cleanProject(name) {
    const slug=String(name || 'default').toLowerCase().replace(/[^a-z0-9]+/g,'-')
        .replace(/^-+|-+$/g,'').slice(0,40).replace(/-+$/,'');
    return slug || 'default';
}

// One page per implemented OpenJarvis capability (01-16). Every action name
// is a real backend/spark_workbench.py ACTION_KEYS entry dispatched through
// the owner-gated `workspace_action` handler; nothing here invents endpoints.
// Read-only status actions exist for all 16; mutating actions are explicit
// owner controls with honest backend policies (approval ids, consent flags,
// owners, budgets), never silently triggered by the UI.
export const CAPABILITY_PAGES = [
    {id:'morning-digest', num:'01', title:'Morning Digest',
     blurb:'Local triage of yesterday\'s Google snapshot plus opt-in RSS; speak or acknowledge the composed digest.',
     status:'digest_status',
     actions:[
        {action:'digest_run', label:'Run digest now', fields:[]},
        {action:'digest_history', label:'Load recent history', fields:[{key:'limit',type:'number',def:10}]},
        {action:'digest_configure', label:'Configure schedule', fields:[{key:'schedule_ist',type:'text',def:'07:00'},{key:'news_enabled',type:'bool',def:false},{key:'news_url',type:'text',def:''}]},
        {action:'digest_speech', label:'Compose speech text', fields:[{key:'digest',type:'json',def:''}]},
        {action:'digest_speak', label:'Play through SPARK voice', fields:[{key:'digest',type:'json',def:''}]},
        {action:'digest_ack', label:'Acknowledge digest', fields:[{key:'digest',type:'json',def:''}]},
     ]},
    {id:'whatsapp', num:'02', title:'WhatsApp Gateway',
     blurb:'WhatsApp Cloud API with an approval nonce, rate limits and replay-protected inbound; nothing enabled by default.',
     status:'hub_status',
     actions:[
        {action:'hub_configure', label:'Configure channel', fields:[{key:'channel',type:'text',def:'whatsapp'},{key:'config',type:'json',def:'{}'}]},
        {action:'hub_disconnect', label:'Disconnect channel', fields:[{key:'channel',type:'text',def:'whatsapp'}]},
        {action:'hub_approve', label:'Approve outbound message', fields:[{key:'channel',type:'text',def:'whatsapp'},{key:'recipient',type:'text',def:''},{key:'text',type:'text',def:''}]},
        {action:'hub_send', label:'Send approved message', fields:[{key:'channel',type:'text',def:'whatsapp'},{key:'approval_id',type:'text',def:''}]},
        {action:'hub_receive', label:'Fetch inbound', fields:[{key:'channel',type:'text',def:'whatsapp'}]},
        {action:'hub_history', label:'Load history', fields:[{key:'limit',type:'number',def:20}]},
     ]},
    {id:'proactive-agent', num:'03', title:'Proactive Agent',
     blurb:'Tiered proposals with dedupe, decided by the owner; restricted tiers are never self-executed and everything is undoable.',
     status:'proactive_summary',
     actions:[
        {action:'proactive_inbox', label:'Open proposal inbox', fields:[{key:'state',type:'text',def:''},{key:'limit',type:'number',def:20}]},
        {action:'proactive_propose', label:'Record a proposal', fields:[{key:'source',type:'text',def:''},{key:'kind',type:'text',def:''},{key:'tier',type:'text',def:''},{key:'detail',type:'text',def:''}]},
        {action:'proactive_decide', label:'Decide proposal', fields:[{key:'dedupe_key',type:'text',def:''},{key:'approved',type:'bool',def:true},{key:'remember',type:'bool',def:false}]},
        {action:'proactive_execute', label:'Execute approved proposal', fields:[{key:'dedupe_key',type:'text',def:''}]},
        {action:'proactive_undo', label:'Undo execution', fields:[{key:'dedupe_key',type:'text',def:''}]},
     ]},
    {id:'opencode-agent', num:'04', title:'OpenCode Agent',
     blurb:'Headless OpenCode sessions inside the scoped repository root, masked transcripts, human patch review, allow-listed tests only.',
     status:'opencode_status',
     actions:[
        {action:'opencode_run', label:'Run headless session', fields:[{key:'prompt',type:'text',def:''},{key:'cwd',type:'text',def:''},{key:'timeout',type:'number',def:300}], note:'Empty work directory (REPO_ROOT scope) runs in the SPARK repository.'},
        {action:'opencode_diff', label:'Capture git patch', fields:[{key:'session',type:'text',def:''}], note:'Empty session captures the repository-scale patch.'},
        {action:'opencode_test', label:'Run allow-listed tests', fields:[{key:'command',type:'text',def:'python -m pytest tests -q'},{key:'cwd',type:'text',def:''}]},
     ]},
    {id:'deep-research', num:'05', title:'Deep Research',
     blurb:'Bounded 2-8 hop traversal over local snapshot and Obsidian corpora with citations and no-evidence honesty.',
     status:'research_run',
     actions:[
        {action:'research_run', label:'Run research', fields:[{key:'question',type:'text',def:''},{key:'max_hops',type:'number',def:4}]},
     ]},
    {id:'messaging-hub', num:'06', title:'Messaging Hub',
     blurb:'Per-channel states across seven providers: allowlisted inbound, rate-limited approved outbound, honest configured-untested reporting.',
     status:'hub_status',
     actions:[
        {action:'hub_history', label:'Load recent channel traffic', fields:[{key:'limit',type:'number',def:20}]},
        {action:'hub_receive', label:'Poll inbound channel', fields:[{key:'channel',type:'text',def:''}]},
        {action:'hub_approve', label:'Approve outbound', fields:[{key:'channel',type:'text',def:''},{key:'recipient',type:'text',def:''},{key:'text',type:'text',def:''}]},
        {action:'hub_send', label:'Send approved', fields:[{key:'channel',type:'text',def:''},{key:'approval_id',type:'text',def:''}]},
     ]},
    {id:'trace-learning', num:'07', title:'Trace Learning',
     blurb:'Masked trace capture with measured labels; policy changes require owner activation and a held-out benchmark gate.',
     status:'trace_status',
     actions:[
        {action:'trace_capture', label:'Capture trace', fields:[{key:'task_class',type:'text',def:''},{key:'model',type:'text',def:''},{key:'payload',type:'json',def:'{}'},{key:'latency_ms',type:'number',def:0},{key:'success',type:'bool',def:true}]},
        {action:'trace_label', label:'Label trace', fields:[{key:'key',type:'text',def:''},{key:'success',type:'bool',def:true}]},
        {action:'trace_labeled', label:'List labeled traces', fields:[{key:'task_class',type:'text',def:''},{key:'limit',type:'number',def:10}]},
        {action:'learning_status', label:'Learning status', fields:[]},
     ]},
    {id:'spec-search', num:'08', title:'Spec Search',
     blurb:'Diagnose, plan, test, gate and record candidate specs; the planner is owner-granted only and stays honestly not configured otherwise.',
     status:'spec_search_status',
     actions:[
        {action:'spec_search_run', label:'Run spec search', fields:[{key:'goal',type:'text',def:''}]},
        {action:'spec_candidates', label:'List candidates', fields:[{key:'status',type:'text',def:''},{key:'limit',type:'number',def:10}]},
        {action:'spec_activate', label:'Activate candidate', fields:[{key:'key',type:'text',def:''},{key:'approved_by',type:'text',def:''}]},
        {action:'spec_rollback', label:'Rollback to baseline', fields:[]},
     ]},
    {id:'skill-ecosystem', num:'09', title:'Skill Ecosystem',
     blurb:'Imported bundles pass license, provenance and sha256 gates; executable code is refused and pipelines only run granted read-only tools.',
     status:'skill_status',
     actions:[
        {action:'skill_list', label:'List imported skills', fields:[]},
        {action:'skill_import', label:'Import manifest', fields:[{key:'manifest',type:'json',def:'{}'},{key:'provided_by',type:'text',def:''}]},
        {action:'skill_review', label:'Review with grants', fields:[{key:'key',type:'text',def:''},{key:'approved_by',type:'text',def:''},{key:'granted_tools',type:'json',def:'[]'}]},
        {action:'skill_run', label:'Run skill pipeline', fields:[{key:'key',type:'text',def:''},{key:'name',type:'text',def:''},{key:'pipeline',type:'json',def:'{}'},{key:'inputs',type:'json',def:'{}'}]},
        {action:'skill_runs', label:'Recent runs', fields:[{key:'key',type:'text',def:''},{key:'limit',type:'number',def:5}]},
        {action:'skill_revoke', label:'Revoke skill', fields:[{key:'key',type:'text',def:''},{key:'approved_by',type:'text',def:''}]},
     ]},
    {id:'agent-runtimes', num:'10', title:'Agent Runtimes',
     blurb:'ReAct, CodeAct and recursive plans refuse before executing; step budgets hold and CodeAct is an AST-allowlisted pure interpreter.',
     status:'agents_status',
     actions:[
        {action:'agents_react', label:'Run ReAct plan', fields:[{key:'goal',type:'text',def:''},{key:'steps',type:'number',def:8},{key:'grant_side_effects',type:'bool',def:false}]},
        {action:'agents_codeact', label:'Run CodeAct snippet', fields:[{key:'code',type:'text',def:''}]},
        {action:'agents_recursive', label:'Run recursive plan', fields:[{key:'goal',type:'text',def:''},{key:'steps',type:'number',def:8},{key:'subgoals',type:'json',def:'[]'}]},
        {action:'agents_runs', label:'Recent runs', fields:[{key:'adapter',type:'text',def:''},{key:'limit',type:'number',def:5}]},
     ]},
    {id:'continuous-monitors', num:'11', title:'Continuous Monitors',
     blurb:'Scoped monitor callbacks with checkpoints, backoff, dedupe, durable cancellation and JSONL notifications with owner receipts.',
     status:'monitor_status',
     actions:[
        {action:'monitor_run', label:'Run monitor now', fields:[{key:'name',type:'text',def:''},{key:'force',type:'bool',def:false}]},
        {action:'monitor_cancel', label:'Cancel monitor', fields:[{key:'name',type:'text',def:''}]},
        {action:'monitor_deliver', label:'Deliver notifications', fields:[{key:'name',type:'text',def:''}]},
        {action:'monitor_acknowledge', label:'Acknowledge events', fields:[{key:'key',type:'text',def:''}]},
     ]},
    {id:'adaptive-routing', num:'12', title:'Adaptive Routing',
     blurb:'Local-first model routing measured from labeled traces; cloud permission stays owner-gated with rollback to always-local.',
     status:'learning_status',
     actions:[
        {action:'router_select', label:'Select routed model', fields:[{key:'task_class',type:'text',def:''},{key:'apply_policy',type:'bool',def:false}]},
        {action:'trace_status', label:'Trace summary', fields:[]},
        {action:'learning_propose', label:'Propose policy', fields:[{key:'name',type:'text',def:''},{key:'policy',type:'text',def:''},{key:'task_class',type:'text',def:''}]},
        {action:'learning_activate', label:'Activate policy', fields:[{key:'key',type:'text',def:''},{key:'approved_by',type:'text',def:''}]},
        {action:'learning_rollback', label:'Rollback policy', fields:[{key:'key',type:'text',def:''}]},
     ]},
    {id:'connector-catalog', num:'13', title:'Connector Catalog',
     blurb:'Two real local connectors ship attached; cloud connectors require the founder\'s consented credentialed session and are never auto-attached.',
     status:'connector_status',
     actions:[
        {action:'connector_attach_local', label:'Attach local adapter', fields:[{key:'id',type:'text',def:''},{key:'provider',type:'text',def:''},{key:'scope',type:'text',def:''}]},
        {action:'connector_configure', label:'Configure account', fields:[{key:'id',type:'text',def:''},{key:'account',type:'text',def:''},{key:'consented',type:'bool',def:true}]},
        {action:'connector_validate', label:'Validate account', fields:[{key:'id',type:'text',def:''}]},
        {action:'connector_read', label:'Verified read', fields:[{key:'id',type:'text',def:''},{key:'limit',type:'number',def:5}]},
        {action:'connector_freshness', label:'Freshness check', fields:[{key:'id',type:'text',def:''},{key:'stale_after_seconds',type:'number',def:86400}]},
        {action:'connector_revoke', label:'Revoke connector', fields:[{key:'id',type:'text',def:''},{key:'approved_by',type:'text',def:''}]},
        {action:'connector_events', label:'Connector events', fields:[{key:'id',type:'text',def:''},{key:'limit',type:'number',def:5}]},
     ]},
    {id:'evaluations', num:'14', title:'Standardized Evaluations',
     blurb:'Seven labeled suites with deterministic scoring, markdown export and provenance; live model runs need an owner-attached runner.',
     status:'eval_status',
     actions:[
        {action:'eval_register', label:'Register candidate', fields:[{key:'name',type:'text',def:''},{key:'provenance',type:'text',def:''}]},
        {action:'eval_run', label:'Run suite', fields:[{key:'name',type:'text',def:''},{key:'suite',type:'text',def:''}]},
        {action:'eval_report', label:'Render report', fields:[{key:'name',type:'text',def:''},{key:'suite',type:'text',def:''}]},
        {action:'eval_export', label:'Export markdown', fields:[{key:'name',type:'text',def:''},{key:'suite',type:'text',def:''}]},
        {action:'eval_history', label:'Run history', fields:[{key:'limit',type:'number',def:10}]},
     ]},
    {id:'inference-telemetry', num:'15', title:'Inference Telemetry',
     blurb:'Measured-only latency and token telemetry; TTFT is streaming-only and energy is refused without a real hardware meter.',
     status:'telemetry_status',
     actions:[
        {action:'telemetry_record', label:'Record measurement', fields:[{key:'model',type:'text',def:''},{key:'latency_ms',type:'number',def:0},{key:'input_tokens',type:'number',def:0},{key:'output_tokens',type:'number',def:0},{key:'source',type:'text',def:'provider_report'}]},
        {action:'telemetry_report', label:'Model report', fields:[{key:'model',type:'text',def:''}]},
        {action:'telemetry_capture', label:'Capture local measurement', fields:[{key:'model',type:'text',def:''},{key:'prompt',type:'text',def:''},{key:'allow_cloud',type:'bool',def:false}]},
     ]},
    {id:'inference-backends', num:'16', title:'Inference Backends',
     blurb:'Honest per-engine states; cloud engines need explicit consent, optional engines need measured RAM and owner opt-in, downloads are refused.',
     status:'backend_describe',
     actions:[
        {action:'backend_probe', label:'Probe engine', fields:[{key:'engine',type:'text',def:''},{key:'consented',type:'bool',def:true}]},
        {action:'backend_generate', label:'Generate with engine', fields:[{key:'engine',type:'text',def:''},{key:'prompt',type:'text',def:''},{key:'consented',type:'bool',def:true}]},
        {action:'backend_opt_in', label:'Opt in with hardware proof', fields:[{key:'engine',type:'text',def:''},{key:'approved_by',type:'text',def:''},{key:'measured_ram_gb',type:'number',def:0}]},
        {action:'backend_events', label:'Engine events', fields:[{key:'engine',type:'text',def:''},{key:'limit',type:'number',def:10}]},
     ]},
];

function castField(field, raw) {
    if(field.type==='number'){
        const trimmed=String(raw).trim();
        if(!trimmed) return '';
        const n=Number(trimmed);
        return Number.isFinite(n)? n:'';
    }
    if(field.type==='json'){
        const text=String(raw).trim();
        return text? JSON.parse(text):'';
    }
    if(field.type==='bool') return raw===true || String(raw).trim().toLowerCase()==='true';
    return String(raw);
}

export function buildPayload(fields, values) {
    const payload={};
    for(const field of fields)
        payload[field.key]=field.type==='bool' ? (values[field.key] ?? field.def) : castField(field, values[field.key]);
    return payload;
}

// Spoken-ready summary of a status result for the page header; honest and
// compact rather than exhaustive (full JSON stays one click away).
export function summarizeStatus(result) {
    if(!result || typeof result!=='object')
        return result===undefined ? '' : String(result);
    const parts=[];
    for(const key of ['policy','honesty','sandbox_note','state'])
        if(typeof result[key]==='string') parts.push(result[key]);
    for(const key of ['runs_recorded','entries','count'])
        if(typeof result[key]==='number') parts.push(`${key.replace(/_/g,' ')}: ${result[key]}`);
    if(Array.isArray(result.engines)) parts.push(`engines: ${result.engines.length}`);
    if(Array.isArray(result.providers)) parts.push(`providers: ${result.providers.length}`);
    if(Array.isArray(result.suites)) parts.push(`suites: ${result.suites.length}`);
    if(Array.isArray(result.adapters)) parts.push(`adapters: ${result.adapters.length}`);
    if(Array.isArray(result.monitors)) parts.push(`monitors listed: ${result.monitors.length}`);
    if(Array.isArray(result.states)) parts.push(`connector states: ${result.states.length}`);
    if(typeof result.active_policy==='string') parts.push(`active policy: ${result.active_policy}`);
    if(typeof result.planner==='string') parts.push(`planner: ${result.planner}`);
    if(typeof result.energy==='string') parts.push(`energy: ${result.energy}`);
    return parts.join(' · ') || 'Status loaded.';
}

export default function CapabilitiesCenter({socket, visible=true, project:rawProject='default'}) {
    const project=useMemo(()=>cleanProject(rawProject),[rawProject]);
    const [pageId,setPageId]=useState(CAPABILITY_PAGES[0].id);
    const [notice,setNotice]=useState('Connect SPARK to exercise the sixteen capability pages.');
    const [working,setWorking]=useState(false);
    const [statusResult,setStatusResult]=useState(null);
    const [lastResult,setLastResult]=useState(null);
    const [values,setValues]=useState({});
    const counter=useRef(0);
    const page=CAPABILITY_PAGES.find(p=>p.id===pageId) || CAPABILITY_PAGES[0];

    const request=(action,payload={})=>{
        if(!socket.connected){setNotice('SPARK backend is not connected.');return;}
        counter.current+=1;
        setWorking(true);
        socket.emit('workspace_action',{workspace_token:socket.workspaceToken,
            request_id:`capabilities-${counter.current}`,action,project,payload});
    };

    useEffect(()=>{
        if(!visible) return undefined;
        const listener=(data)=>{
            if(!data || typeof data.action!=='string' || !data.request_id?.startsWith('capabilities-')) return;
            setWorking(false);
            if(!data.ok){setNotice(`${data.action.replace(/_/g,' ')} was refused: ${String(data.message||'action failed.')}`);return;}
            setLastResult(data.result || null);
            if(data.action===page?.status) setStatusResult(data.result || null);
            setNotice(`${data.action.replace(/_/g,' ')} completed for ${project}.`);
        };
        socket.on('workspace_result',listener);
        return ()=>{socket.off?.('workspace_result',listener);};
    },[socket,visible,page?.status,project]);

    useEffect(()=>{
        if(!visible) return;
        setStatusResult(null);
        setValues({});
        setLastResult(null);
        if(page.status==='research_run'){
            // research_run needs a real question; auto-dispatching with an
            // empty one would only manufacture a refusal.
            setNotice('Enter a research question and press Run.');
        } else if(socket.connected) request(page.status);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    },[pageId,visible]);

    function fieldCell(field) {
        if(field.type==='bool')
            return <label className="flex items-center gap-2 text-sm text-cyan-100">
                <input type="checkbox" checked={values[field.key] ?? field.def}
                    onChange={event=>setValues(v=>({...v,[field.key]:event.target.checked}))}/>
                {field.label ?? field.key}</label>;
        if(field.type==='json')
            return <textarea className={inputStyle+' font-mono min-h-[2.5rem]'} rows={field.key==='manifest'? 6:3}
                placeholder={field.note||field.key}
                value={values[field.key] ?? (field.def!==''? field.def:'')}
                onChange={event=>setValues(v=>({...v,[field.key]:event.target.value}))}/>;
        return <input type={field.type==='number'?'number':'text'} className={inputStyle}
            placeholder={field.key}
            value={values[field.key] ?? field.def}
            onChange={event=>setValues(v=>({...v,[field.key]:event.target.value}))}/>;
    }

    function runAction(spec) {
        try {
            const payload=buildPayload(spec.fields, values);
            request(spec.action,payload);
        } catch(error) {
            setNotice(`Invalid ${spec.action} arguments: JSON fields must parse correctly.`);
        }
    }

    const statusText=summarizeStatus(statusResult);
    return (
        <section className="rounded-2xl border border-cyan-500/50 bg-slate-950/95 p-4 text-white shadow-2xl"
            role="region" aria-label="SPARK capabilities center">
            <div className="flex items-center justify-between gap-2">
                <div>
                    <div className="text-xs tracking-widest text-cyan-400">SPARK / capabilities / {project}</div>
                    <h2 className="text-xl font-bold">Capabilities Center</h2>
                    <p className="text-sm text-slate-300">Sixteen OpenJarvis capabilities, each on its own page and dispatching through the owner-gated workbench.</p>
                </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
                {CAPABILITY_PAGES.map(entry=>(
                    <button key={entry.id} type="button" className={buttonStyle}
                        aria-selected={pageId===entry.id} onClick={()=>setPageId(entry.id)}>
                        {entry.num} · {entry.title}</button>
                ))}
            </div>
            <div className="mt-3 rounded-lg bg-cyan-950/40 px-3 py-2 text-sm text-cyan-100" role="status">
                {working? 'Running capability action…':notice}</div>
            <div className="mt-3 grid gap-3 lg:grid-cols-[16rem_1fr]">
                <div className={panelStyle}>
                    <h3 className="text-sm font-semibold text-cyan-200">{page.num} · {page.title}</h3>
                    <p className="mt-1 text-xs text-slate-300">{page.blurb}</p>
                    <button type="button" className={buttonStyle+' mt-2'} disabled={working}
                        onClick={()=>request(page.status)}>Refresh status</button>
                    {statusResult!==null && <div className="mt-2 text-xs text-cyan-200">{statusText}</div>}
                </div>
                <div className="space-y-3">
                    {page.actions.map(spec=>(
                        <div key={spec.action} className={panelStyle}>
                            <div className="flex items-center justify-between gap-2">
                                <code className="text-xs text-amber-200">{spec.action}</code>
                                <button type="button" className={buttonStyle} disabled={working}
                                    onClick={()=>runAction(spec)}>{spec.label}</button>
                            </div>
                            {spec.fields.length>0 &&
                                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                                    {spec.fields.map(field=><div key={field.key}>{fieldCell(field)}</div>)}
                                </div>}
                            {spec.note && <p className="mt-1 text-xs text-slate-400">{spec.note}</p>}
                        </div>
                    ))}
                    {lastResult && <div className={panelStyle}>
                        <h3 className="text-sm font-semibold text-cyan-200">Last result</h3>
                        <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words text-xs text-slate-300"
                            style={{fontFamily:'monospace'}}>
                            {JSON.stringify(lastResult,null,2).slice(0,4000)}</pre>
                    </div>}
                </div>
            </div>
        </section>
    );
}
