import React, {useEffect, useMemo, useRef, useState} from 'react';
import EvolutionPanel from './EvolutionPanel';
import WorkbenchPanel from './WorkbenchPanel';
import IntegrationSyncPanel from './IntegrationSyncPanel';
import ExecutiveBriefingPanel from './ExecutiveBriefingPanel';
import CapabilitiesCenter from './CapabilitiesCenter';
const IntelligenceConsole=React.lazy(()=>import('./IntelligenceConsole'));
const SparkScreens=React.lazy(()=>import('./SparkScreens'));

const buttonStyle = 'rounded-lg border border-cyan-600/50 bg-cyan-950/50 px-3 py-2 text-sm font-semibold text-cyan-100 hover:bg-cyan-800/60 disabled:opacity-40';
const panelStyle = 'rounded-xl border border-cyan-500/20 bg-black/40 p-3';

function cleanProject(name) {
    const slug=String(name || 'default').toLowerCase().replace(/[^a-z0-9]+/g,'-')
        .replace(/^-+|-+$/g,'').slice(0,40).replace(/-+$/,'');
    return slug || 'default';
}

// Genuine ARKUS-powered, offline project knowledge and declarative skill controls.
// Operations go only through the currently authorized local SPARK Socket.IO owner.
export default function WorkspacePanel({socket,visible,project:rawProject,onClose,embedded=false,initialTab='home',initialScreen,initialIntelligencePage='Agents'}) {
    const project=useMemo(() => cleanProject(rawProject),[rawProject]);
    const [tab,setTab]=useState(initialTab);
    const [intelligencePage,setIntelligencePage]=useState(initialIntelligencePage);
    const openIntelligence=page=>{setIntelligencePage(page);setTab('intelligence');};
    const [query,setQuery]=useState('');
    const [documents,setDocuments]=useState([]);
    const [published,setPublished]=useState([]);
    const [hits,setHits]=useState([]);
    const [skills,setSkills]=useState([]);
    const [notice,setNotice]=useState('Connect SPARK to unlock local workspace operations.');
    const [working,setWorking]=useState(false);
    const [skillDraft,setSkillDraft]=useState(JSON.stringify({
        name:'frame_area',description:'Calculate rectangular layup area',
        operation:'multiply',inputs:['length','width'],output:'Area (square units)',
        tests:[{parameters:{length:2,width:3},expected:6}]
    },null,2));
    const [runName,setRunName]=useState('');
    const [runInputs,setRunInputs]=useState('{"length":2,"width":3}');
    const [revisionId,setRevisionId]=useState('');
    const counter=useRef(0);

    const request=(action,payload={})=>{
        if(!socket.connected) {setNotice('SPARK backend is not connected.');return;}
        counter.current+=1;
        setWorking(true);
        socket.emit('workspace_action',{workspace_token:socket.workspaceToken,
            request_id:`workspace-${counter.current}`,action,project,payload
        });
    };

    useEffect(()=>{
        if(!visible) return undefined;
        const listener=(data)=>{
            if(!data || typeof data.action!=='string' || !data.request_id?.startsWith('workspace-')) return;
            setWorking(false);
            if(!data.ok) {setNotice(String(data.message||'Workspace action failed.'));return;}
            const result=data.result;
            setNotice('Ready. Local workspace connected.');
            if(data.action==='list_documents') {setDocuments(Array.isArray(result)?result:[]);return;}
            if(data.action==='list_holo_notes') {setPublished(Array.isArray(result)?result:[]);return;}
            if(data.action==='list_skills') {setSkills(Array.isArray(result)?result:[]);return;}
            if(data.action==='publish_vayu_snapshot'){
                setNotice(`Published ${result.documents} notes and ${result.tasks} tasks for ${project}. In VAYU, open Spark project data. Refresh this snapshot after changes.`);
                return;
            }
            if(data.action==='search_documents') {
                setHits(Array.isArray(result)?result:[]);
                setNotice(`Found ${Array.isArray(result)?result.length:0} matching document(s) in ${project}.`);
                return;
            }
            if(data.action==='run_skill') {
                setNotice(`${result?.skill||'Skill'} = ${result?.result} (${result?.output||'Result'})`);
                return;
            }
            setNotice(`${data.action.replace(/_/g,' ')} completed for ${project}.`);
            if(['import_document','remove_document'].includes(data.action)) {
                request('list_documents');
                if(data.action==='remove_document') {
                    request('list_holo_notes');
                    setHits([]);
                }
            }
            if(['publish_holo_note','unpublish_holo_note'].includes(data.action)) {
                request('list_holo_notes');
            }
            if(['propose_skill','test_skill','activate_skill','revise_skill','rollback_skill'].includes(data.action))
                request('list_skills');
        };
        socket.on('workspace_result',listener);
        request('list_documents');
        request('list_holo_notes');
        request('list_skills');
        return ()=>socket.off('workspace_result',listener);
    },[socket,visible,project]);

    if(!visible) return null;

    async function upload(event) {
        const file=event.target.files?.[0];
        event.target.value='';
        if(!file)return;
        if(file.size<1 || file.size>2_000_000 || !/\.(txt|md|markdown|docx|pdf)$/i.test(file.name)){
            setNotice('Choose TXT, MD, DOCX or text PDF, 2 MB maximum.');return;
        }
        try {
            const data=await file.arrayBuffer();
            request('import_document',{name:file.name,data});
        } catch {setNotice('Document could not be read.');}
    }

    function submitSkill() {
        try {
            const spec=JSON.parse(skillDraft);
            request(revisionId?'revise_skill':'propose_skill',
                revisionId?{id:revisionId,spec}:{spec});
            setRevisionId('');
        } catch {setNotice('Skill specification must be valid JSON.');}
    }

    function runSkill() {
        try {request('run_skill',{name:runName.trim(),params:JSON.parse(runInputs)});}
        catch {setNotice('Skill arguments must be a JSON object.');}
    }

    return (
        <section className={embedded ? `cc-embedded-workspace ${tab==='knowledge' ? 'cc-knowledge-workspace' : ''} text-white` : 'relative z-40 mx-3 my-2 max-h-[calc(100vh-7rem)] overflow-y-auto rounded-2xl border border-cyan-500/50 bg-slate-950/95 p-4 text-white shadow-2xl'}
            role="region" aria-label="SPARK knowledge and skill workspace">
            {!embedded && <><div className="flex items-center justify-between gap-2">
                <div>
                    <div className="text-xs tracking-widest text-cyan-400">SPARK / {project}</div>
                    <h2 className="text-xl font-bold">Your SPARK workspace</h2>
                    <p className="text-sm text-slate-300">Tasks, knowledge, tools and improvements in one place. Current project: <strong>{project}</strong></p>
                </div>
                <button type="button" className={buttonStyle} onClick={onClose}>Voice cockpit</button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2" role="tablist">
                <button type="button" role="tab" aria-selected={tab==='home'} className={buttonStyle} onClick={()=>setTab('home')}>Home</button>
                <button type="button" role="tab" aria-selected={tab==='screens'} className={buttonStyle} onClick={()=>setTab('screens')}>Command Center</button>
                <button type="button" role="tab" aria-selected={tab==='knowledge'} className={buttonStyle} onClick={()=>setTab('knowledge')}>Document knowledge</button>
                <button type="button" role="tab" aria-selected={tab==='skills'} className={buttonStyle} onClick={()=>setTab('skills')}>Skill Forge</button>
                <button type="button" role="tab" aria-selected={tab==='evolution'} className={buttonStyle} onClick={()=>setTab('evolution')}>Recovery &amp; REA</button>
                <button type="button" role="tab" aria-selected={tab==='workbench'} className={buttonStyle} onClick={()=>setTab('workbench')}>Workbench</button>
                <button type="button" role="tab" aria-selected={tab==='intelligence'} className={buttonStyle} onClick={()=>setTab('intelligence')}>Intelligence</button>
                <button type="button" role="tab" aria-selected={tab==='capabilities'} className={buttonStyle} onClick={()=>setTab('capabilities')}>Capabilities</button>
            </div>
            </>}
            {(!embedded || ['knowledge','skills'].includes(tab)) && <p role="status" className="mt-3 rounded-lg bg-cyan-950/40 px-3 py-2 text-sm text-cyan-100">{notice}</p>}
            {tab==='knowledge'&&<IntegrationSyncPanel socket={socket}/>}
            {tab==='screens' ? <React.Suspense fallback={<p role="status">Loading SPARK screens…</p>}><SparkScreens socket={socket} project={project} onCockpit={onClose} initialPage={initialScreen} compactNavigation={embedded}/></React.Suspense> : tab==='home' ? <div className="mt-4 space-y-4">
                <ExecutiveBriefingPanel socket={socket}/>
                <div><h3 className="text-2xl font-semibold">Your project starts here</h3><p className="mt-1 text-slate-300">Bring in knowledge, run reviewed agents, and inspect Spark's health.</p></div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {[
                        ['Tasks and schedules','Create, review and schedule actions.',()=>openIntelligence('Agents')],
                        ['Your documents','Import and search project documents.',()=>setTab('knowledge')],
                        ['Your tools','Use and manage SPARK skills.',()=>setTab('skills')],
                        ['Improve SPARK','Review repairs and learn from repositories.',()=>setTab('evolution')],
                        ['Connections','Check the status of configured services.',()=>openIntelligence('Integrations')],
                    ].map(([label,description,open])=><button key={label} type="button" onClick={open} className={`${panelStyle} text-left hover:border-cyan-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-300`}><span className="block font-semibold text-cyan-100">{label}</span><span className="mt-1 block text-sm text-slate-300">{description}</span></button>)}
                </div>
                <p className="text-sm text-slate-400">Choose a plan to review before execution. Models and external connections use your existing configuration.</p>
            </div> : tab==='knowledge' ? (
                <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    <div className={panelStyle}>
                        <h3 className="font-semibold mb-2">Indexed files ({documents.length}/50)</h3>
                        <p className="text-sm text-slate-300 mb-2">Choose <strong>Publish to HOLO</strong> for each document you want accessible in the original gesture deck and Brain Map. No other files are exposed.</p>
                        <label className="block text-sm text-cyan-200 mb-2">
                            Import chosen document (local only, up to 2 MB)
                            <input type="file" accept=".txt,.md,.markdown,.docx,.pdf" onChange={upload} className="block w-full mt-2 text-sm"/>
                        </label>
                        <button type="button" className={buttonStyle} onClick={()=>request('list_documents')}>Refresh files</button>
                        <div className="mt-2 max-h-48 overflow-auto space-y-2">
                            {documents.length ? documents.map(doc=><div key={doc.id} className="flex justify-between items-center gap-2 border-b border-white/10 py-2 text-sm">
                                <span className="break-all">{doc.name} <span className="text-slate-400">({doc.characters} characters)</span></span>
                                <div className="flex flex-wrap gap-1">
                                    {published.some(note=>note.id===doc.id) ? (
                                        <button type="button" className={buttonStyle}
                                            onClick={()=>request('unpublish_holo_note',{id:doc.id})}>
                                            Unpublish HOLO
                                        </button>
                                    ) : (
                                        <button type="button" className={buttonStyle}
                                            onClick={()=>request('publish_holo_note',{id:doc.id})}>
                                            Publish to HOLO
                                        </button>
                                    )}
                                    <button type="button" className={buttonStyle}
                                        onClick={()=>{if(window.confirm('Delete this indexed document and revoke its HOLO copy?'))request('remove_document',{id:doc.id});}}>
                                        Remove
                                    </button>
                                </div>
                            </div>) : <p className="text-sm text-slate-400">No documents indexed in this project.</p>}
                        </div>
                    </div>
                    <div className={panelStyle}>
                        <h3 className="font-semibold mb-2">Search actual document contents</h3>
                        <div className="flex gap-2">
                            <input aria-label="Search project knowledge" className="min-w-0 flex-1 rounded-lg bg-slate-900 border border-white/20 p-2 text-sm"
                                placeholder="e.g. T700S coupon" value={query} onChange={e=>setQuery(e.target.value)}
                                onKeyDown={e=>{if(e.key==='Enter' && query.trim())request('search_documents',{query:query.trim()});}}/>
                            <button type="button" className={buttonStyle} onClick={()=>query.trim()&&request('search_documents',{query:query.trim()})}>Search</button>
                        </div>
                        <div className="mt-2 max-h-64 overflow-auto space-y-2">
                            {hits.map(hit=><div key={hit.id} className="rounded-lg border border-white/10 p-2 text-sm">
                                <strong className="text-cyan-300">{hit.title}</strong>
                                <p className="mt-1 whitespace-pre-wrap break-words text-slate-200">{hit.excerpt}</p>
                            </div>)}
                        </div>
                    </div>
                </div>
            ) : tab==='evolution' ? <EvolutionPanel socket={socket} project={project} /> : tab==='workbench' ? <WorkbenchPanel socket={socket} project={project} /> : tab==='intelligence' ? <React.Suspense fallback={<p role="status">Loading intelligence controls…</p>}><IntelligenceConsole socket={socket} project={project} initialPage={intelligencePage} compactNavigation={embedded}/></React.Suspense> : tab==='capabilities' ? <CapabilitiesCenter socket={socket} project={project}/> : (
                <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    <div className={panelStyle}>
                        <h3 className="font-semibold mb-2">Skill specification (declarative JSON only)</h3>
                        <textarea aria-label="Skill specification JSON" rows={8} value={skillDraft}
                            onChange={e=>setSkillDraft(e.target.value)}
                            className="w-full rounded-lg bg-slate-900 border border-white/20 p-2 text-sm font-mono"/>
                        <button type="button" className={buttonStyle} onClick={submitSkill}>
                            {revisionId?'Propose revision':'Propose new skill'}
                        </button>
                        {revisionId&&<button type="button" className={buttonStyle} onClick={()=>setRevisionId('')}>Cancel revision</button>}
                        <p className="text-xs text-slate-400 mt-2">No arbitrary code. Only add, subtract, multiply, divide, percentage, average and clamp.</p>
                    </div>
                    <div className={panelStyle}>
                        <h3 className="font-semibold mb-2">Skill lifecycle ({skills.length}/40)</h3>
                        <button type="button" className={buttonStyle} onClick={()=>request('list_skills')}>Refresh skills</button>
                        <div className="mt-2 max-h-52 overflow-auto space-y-2">
                            {skills.map(skill=><div key={skill.id} className="rounded-lg border border-white/10 p-2 text-sm">
                                <div className="font-semibold text-cyan-200">{skill.name} — {skill.status}, rev {skill.revision||1}</div>
                                <p className="text-slate-400">{skill.operation}({skill.inputs.join(', ')})</p>
                                <p className="text-xs text-slate-400 select-all">Revision ID: {skill.id}</p>
                                <div className="flex flex-wrap gap-1 mt-2">
                                    {skill.status!=='active' && <button type="button" className={buttonStyle} onClick={()=>request('test_skill',{id:skill.id})}>Test</button>}
                                    {skill.status==='tested' && <button type="button" className={buttonStyle} onClick={()=>request('activate_skill',{id:skill.id})}>Activate</button>}
                                    {skill.status==='active' && <button type="button" className={buttonStyle} onClick={()=>{setRevisionId(skill.id);setSkillDraft(JSON.stringify({name:skill.name,description:skill.description,operation:skill.operation,inputs:skill.inputs,output:skill.output,tests:skill.tests||[]},null,2));}}>Revise</button>}
                                    {skill.status==='active' && skill.supersedes && <button type="button" className={buttonStyle} onClick={()=>request('rollback_skill',{id:skill.id})}>Rollback</button>}
                                    {skill.status==='active' && <button type="button" className={buttonStyle} onClick={()=>{setRunName(skill.name);setRunInputs(JSON.stringify(Object.fromEntries(skill.inputs.map(n=>[n,1]))));}}>Prepare run</button>}
                                </div>
                            </div>)}
                            {!skills.length && <p className="text-sm text-slate-400">No skills in this project.</p>}
                        </div>
                        <h3 className="font-semibold my-2">Execute an activated skill</h3>
                        <input aria-label="Skill name" value={runName} onChange={e=>setRunName(e.target.value)} placeholder="Skill name" className="w-full rounded-lg bg-slate-900 border border-white/20 p-2 text-sm"/>
                        <textarea aria-label="Skill numeric inputs JSON" rows={2} value={runInputs} onChange={e=>setRunInputs(e.target.value)} className="mt-2 w-full rounded-lg bg-slate-900 border border-white/20 p-2 text-sm font-mono"/>
                        <button type="button" disabled={!runName||working} className={buttonStyle} onClick={runSkill}>Run locally</button>
                    </div>
                </div>
            )}
        </section>
    );
}
