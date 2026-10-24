import React, {useEffect, useRef, useState} from 'react';

const button = 'rounded-lg border border-cyan-600/50 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-900/40 disabled:opacity-40';
const input = 'w-full rounded-lg border border-white/20 bg-slate-900 p-2 text-sm';
const card = 'space-y-3 rounded-xl border border-cyan-500/20 bg-black/20 p-4';
const officeExample = {title:'Project brief', sections:[{heading:'Overview',text:'Describe the project and its goals.',bullets:['Scope','Milestones'],notes:'Introduce the project.'}]};
const sheetExample = {title:'Project costs',sheets:[{name:'Budget',rows:[['Item','Amount'],['Materials',120],['Assembly',80],['Total',{formula:'=SUM(B2:B3)'}]],chart:true}]};
const robotExample = {links:[0.3,0.25],steps:[{type:'move',target:[0.3,0,0.2],seconds:1},{type:'gripper',state:'closed'},{type:'delay',seconds:0.5},{type:'move',target:[0.2,0.2,0.2],seconds:1}]};

export default function WorkbenchPanel({socket, project}) {
    const [tab,setTab] = useState('agenda');
    const [busy,setBusy] = useState(false);
    const [notice,setNotice] = useState('Choose a workspace tool.');
    const [snapshot,setSnapshot] = useState({preference:[],agenda:[],routine:[]});
    const [prefKey,setPrefKey] = useState('');
    const [prefValue,setPrefValue] = useState('');
    const [title,setTitle] = useState('');
    const [due,setDue] = useState('');
    const [kind,setKind] = useState('reminder');
    const [routineTitle,setRoutineTitle] = useState('System check');
    const [steps,setSteps] = useState(JSON.stringify([{action:'get_system_status',args:{}}],null,2));
    const [format,setFormat] = useState('docx');
    const [spec,setSpec] = useState(JSON.stringify(officeExample,null,2));
    const [officePrompt,setOfficePrompt] = useState('');
    const [artifacts,setArtifacts] = useState([]);
    const [pdfIds,setPdfIds] = useState([]);
    const [pages,setPages] = useState('');
    const [robot,setRobot] = useState(JSON.stringify(robotExample,null,2));
    const [simulation,setSimulation] = useState(null);
    const [frame,setFrame] = useState(0);
    const [playing,setPlaying] = useState(false);
    const [start,setStart] = useState('19.076,72.8777');
    const [end,setEnd] = useState('51.5074,-0.1278');
    const [route,setRoute] = useState(null);
    const [clipboard,setClipboard] = useState('');
    const [services,setServices] = useState([]);
    const [service,setService] = useState('');
    const [tools,setTools] = useState([]);
    const [tool,setTool] = useState('');
    const [args,setArgs] = useState('{}');
    const [knowledgeQuery,setKnowledgeQuery] = useState('VAOS');
    const [notePath,setNotePath] = useState('VAOS.md');
    const [knowledgeResult,setKnowledgeResult] = useState(null);
    const [image,setImage] = useState(null);
    const [question,setQuestion] = useState('Describe the selected screenshot.');
    const pending = useRef(null);
    const deadline = useRef(null);

    function request(action,payload={}) {
        if (pending.current) return;
        if (!socket.connected) {setNotice('Connect SPARK first.');return;}
        const requestId=`workbench-${Date.now()}-${Math.random().toString(36).slice(2,8)}`;
        pending.current=requestId;
        setBusy(true);setNotice('Working…');
        clearTimeout(deadline.current);
        deadline.current=setTimeout(()=>{pending.current=null;setBusy(false);setNotice('Request timed out. Refresh stored results before retrying.');},180000);
        socket.emit('workspace_action',{workspace_token:socket.workspaceToken,request_id:requestId,action,project,payload});
    }

    useEffect(()=>{
        pending.current=null;setBusy(false);setImage(null);
        setSnapshot({preference:[],agenda:[],routine:[]});setArtifacts([]);setPdfIds([]);
        setKnowledgeResult(null);
        const receive=response=>{
            if(response?.request_id!==pending.current)return;
            clearTimeout(deadline.current);pending.current=null;setBusy(false);
            if(!response.ok){setNotice(String(response.message||'Workbench operation failed.'));return;}
            const {action,result}=response;
            if(['knowledge_notes','knowledge_note','mcp_call'].includes(action))setKnowledgeResult({action,result});
            if(action==='workbench_snapshot')setSnapshot(result);
            if(action==='list_artifacts'){setArtifacts(result);setNotice(`${result.length} local files.`);return;}
            if(action==='list_integrations'){setServices(result);setService(result[0]?.name||'');setTools([]);setTool('');setNotice(result.length?`${result.length} configured services.`:'No MCP services configured. Add a trusted server on the host to connect one.');return;}
            if(action==='mcp_discover'){setTools(result);setTool(result[0]?.name||'');setNotice(`${result.length} service tools discovered. Select a tool to inspect its arguments.`);return;}
            if(action==='simulate_robot'){setSimulation(result);setFrame(0);setPlaying(false);setNotice(`Simulation ready: ${result.frames.length} frames over ${result.seconds.toFixed(1)} seconds.`);return;}
            if(action==='calculate_route'){setRoute(result);setNotice(`Geometric route calculated: ${result.distance_km.toLocaleString()} km.`);return;}
            if(action==='transform_text'&&typeof result.text==='string')setClipboard(result.text);
            if(action==='download_artifact'){
                const url=URL.createObjectURL(new Blob([result.data],{type:result.mime}));
                const anchor=document.createElement('a');anchor.href=url;anchor.download=result.name;anchor.click();
                setTimeout(()=>URL.revokeObjectURL(url),30000);
                setNotice(`Downloaded ${result.name}`);return;
            }
            if(['save_preference','add_agenda','complete_agenda','remove_workbench_item','create_routine','advance_routine'].includes(action)){
                pending.current=`${response.request_id}-refresh`;setBusy(true);
                deadline.current=setTimeout(()=>{pending.current=null;setBusy(false);setNotice('Refresh timed out. Try refreshing the workspace.');},15000);
                socket.emit('workspace_action',{workspace_token:socket.workspaceToken,request_id:`${response.request_id}-refresh`,action:'workbench_snapshot',project,payload:{}});
            }
            if(['create_office','generate_office','import_pdf','pdf_operation'].includes(action)&&result.id){
                setArtifacts(previous=>[...previous.filter(a=>a.id!==result.id),result]);
                setNotice(`Ready: ${result.name}. Download below.`);return;
            }
            const output=action==='analyze_snapshot'?result.answer:action==='pdf_operation'&&result.text?result.text:JSON.stringify(result,null,2);
            setNotice(action==='workbench_snapshot'?'Local workspace refreshed.':output.slice(0,20000));
        };
        const disconnect=()=>{clearTimeout(deadline.current);pending.current=null;setBusy(false);setNotice('Backend disconnected. Refresh when reconnected.');};
        socket.on('workspace_result',receive);socket.on('disconnect',disconnect);
        request('workbench_snapshot');
        return()=>{clearTimeout(deadline.current);socket.off('workspace_result',receive);socket.off('disconnect',disconnect);};
    },[socket,project]);

    useEffect(()=>{
        if(!playing||!simulation)return undefined;
        if(frame>=simulation.frames.length-1){setPlaying(false);return undefined;}
        const previous=frame?simulation.frames[frame-1].time:0;
        const timer=setTimeout(()=>setFrame(value=>Math.min(value+1,simulation.frames.length-1)),Math.max(10,(simulation.frames[frame].time-previous)*1000));
        return()=>clearTimeout(timer);
    },[playing,frame,simulation]);

    function jsonAction(action,raw,key) {
        try {request(action,{[key]:JSON.parse(raw)});}catch{setNotice('Enter valid JSON.');}
    }
    async function uploadPdf(event) {
        const file=event.target.files?.[0];event.target.value='';if(!file)return;
        if(file.size>2000000){setNotice('Select a PDF of at most 2 MB.');return;}
        request('import_pdf',{name:file.name.slice(0,100),data:await file.arrayBuffer()});
    }
    async function selectImage(event) {
        const file=event.target.files?.[0];event.target.value='';if(!file)return;
        if(file.size>5000000||!['image/jpeg','image/png'].includes(file.type)){setNotice('Choose a JPEG or PNG of at most 5 MB.');return;}
        try {
            const bitmap=await createImageBitmap(file);
            const ratio=Math.min(1,1600/Math.max(bitmap.width,bitmap.height));
            const canvas=document.createElement('canvas');canvas.width=Math.round(bitmap.width*ratio);canvas.height=Math.round(bitmap.height*ratio);
            const context=canvas.getContext('2d');context.fillStyle='#fff';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
            setImage(canvas.toDataURL('image/jpeg',.8));setNotice('Image selected locally. Choose Analyze to send it to Groq.');
        }catch{setNotice('Image could not be decoded.');}
    }
    const current=simulation?.frames[frame];
    const armPoint=point=>{
        const scale=110/(simulation.links[0]+simulation.links[1]);
        const yaw=current.angles[0]*Math.PI/180;
        return [180+(point[0]*Math.cos(yaw)+point[1]*Math.sin(yaw))*scale,130-point[2]*scale];
    };
    const selectedTool=tools.find(value=>value.name===tool);
    return <div className="mt-3 space-y-4">
        <nav aria-label="Workbench tools" className="flex flex-wrap gap-2">
            {[['agenda','Agenda & memory'],['routines','Routines'],['office','Office & PDFs'],['lab','Robot & routes'],['knowledge','Connected knowledge'],['services','Services & context']].map(([id,label])=><button type="button" key={id} className={button} aria-pressed={tab===id} onClick={()=>{setTab(id);setPlaying(false);}}>{label}</button>)}
        </nav>
        <pre role="status" aria-live="polite" className="max-h-36 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-cyan-950/30 p-3 text-sm">{notice}</pre>
        {tab==='knowledge'&&<section className={card}>
            <h3 className="font-semibold">Graphify, Graphiti and Obsidian</h3>
            <p className="text-sm text-slate-300">Project: {project}. Graphify searches code architecture. Graphiti searches recorded history. Obsidian searches local notes. Source results appear above.</p>
            <input aria-label="Knowledge question" className={input} value={knowledgeQuery} maxLength={200} onChange={e=>setKnowledgeQuery(e.target.value)} placeholder="Ask about VAOS, Vyndi OS, or a code symbol"/>
            <div className="flex flex-wrap gap-2">
                <button className={button} disabled={busy||!knowledgeQuery.trim()} onClick={()=>request('mcp_call',{server:'graphify',name:'query_graph',arguments:{question:knowledgeQuery,mode:'bfs',depth:2,token_budget:1800}})}>Search Graphify code</button>
                <button className={button} disabled={busy||knowledgeQuery.trim().length<3} onClick={()=>request('mcp_call',{server:'graphiti',name:'search_temporal_facts',arguments:{question:knowledgeQuery,limit:6}})}>Search Graphiti history</button>
                <button className={button} disabled={busy||!knowledgeQuery.trim()} onClick={()=>request('mcp_call',{server:'graphiti',name:'get_entity_timeline',arguments:{entity:knowledgeQuery.slice(0,120)}})}>Entity timeline</button>
                <button className={button} disabled={busy||!knowledgeQuery.trim()} onClick={()=>request('knowledge_notes',{query:knowledgeQuery})}>Search Obsidian notes</button>
                <button className={button} disabled={busy} onClick={()=>request('mcp_call',{server:'graphiti',name:'graph_status',arguments:{}})}>Graphiti status</button>
            </div>
            <p className="text-xs text-slate-400">Extract next batch sends up to 12 pending project records to configured Groq and Gemini providers. Repeat while remaining is above zero. Extracted associations need source verification.</p>
            <button className={button} disabled={busy} onClick={()=>request('mcp_call',{server:'graphiti',name:'refresh_project_graph',arguments:{}})}>Extract next Graphiti batch</button>
            <input aria-label="Obsidian note path" className={input} value={notePath} onChange={e=>setNotePath(e.target.value)} placeholder="VAOS.md"/>
            <button className={button} disabled={busy||!notePath.trim()} onClick={()=>request('knowledge_note',{path:notePath})}>Read Obsidian note</button>
            {knowledgeResult&&<div className="mt-4 space-y-3" aria-label="Knowledge results">
                {knowledgeResult.action==='knowledge_notes'&&Array.isArray(knowledgeResult.result)?<>
                    {knowledgeResult.result.length===0&&<p>No matching notes in the configured vault.</p>}
                    {knowledgeResult.result.map(note=><article key={note.path} className="rounded-lg border border-white/10 p-3">
                        <button className={button} disabled={busy} onClick={()=>{setNotePath(note.path);request('knowledge_note',{path:note.path});}}>{note.name}</button>
                        <p className="break-all text-xs text-slate-400">{note.path}</p><p className="whitespace-pre-wrap text-sm">{note.snippet}</p>
                    </article>)}
                </>:<pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-950 p-3 text-sm">{knowledgeResult.result?.text||knowledgeResult.result?.content?.filter(part=>part.type==='text').map(part=>part.text).join('\n')||JSON.stringify(knowledgeResult.result,null,2)}</pre>}
            </div>}
        </section>}
        {tab==='agenda'&&<div className="grid gap-4 lg:grid-cols-2">
            <section className={card}><h3 className="font-semibold">Project preferences</h3><p className="text-sm text-slate-300">Explicit local memory. In Groq voice, say “Remember my units as metric” or “Show my preferences”.</p>
                <input aria-label="Preference name" className={input} value={prefKey} onChange={e=>setPrefKey(e.target.value)} placeholder="Preference, e.g. units"/>
                <input aria-label="Preference value" className={input} value={prefValue} onChange={e=>setPrefValue(e.target.value)} placeholder="Value, e.g. metric"/>
                <button className={button} disabled={busy||!prefKey||!prefValue} onClick={()=>request('save_preference',{key:prefKey,value:prefValue})}>Save preference</button>
                {snapshot.preference.map(item=><div key={item.id} className="flex flex-wrap items-center justify-between gap-2 text-sm"><span>{item.key}: {item.value}</span><button className={button} disabled={busy} onClick={()=>request('remove_workbench_item',{kind:'preference',id:item.id})}>Remove</button></div>)}
            </section>
            <section className={card}><h3 className="font-semibold">Reminders and local calendar</h3><p className="text-sm text-slate-300">Due items appear while this project is connected. Missed reminders remain in the agenda. Voice: “Remind me in 10 minutes to review the design”.</p>
                <input aria-label="Agenda title" className={input} value={title} onChange={e=>setTitle(e.target.value)} placeholder="Title"/>
                <label className="block text-sm">Due in your local timezone<input aria-label="Agenda date and time" type="datetime-local" className={input} value={due} onChange={e=>setDue(e.target.value)}/></label>
                <select aria-label="Agenda type" className={input} value={kind} onChange={e=>setKind(e.target.value)}><option value="reminder">Reminder</option><option value="event">Calendar event</option></select>
                <button className={button} disabled={busy||!title||!due} onClick={()=>request('add_agenda',{title,due:new Date(due).toISOString(),kind})}>Add to agenda</button>
                <button className={button} disabled={busy} onClick={()=>request('workbench_snapshot')}>Refresh</button>
                {snapshot.agenda.map(item=><div key={item.id} className="space-y-1 rounded border border-white/10 p-2 text-sm"><strong>{item.title}</strong><p>{new Date(item.due).toLocaleString()} · {item.done?'Complete':item.kind}</p><div className="flex gap-2"><button className={button} disabled={busy} onClick={()=>request('complete_agenda',{id:item.id,done:!item.done})}>{item.done?'Reopen':'Complete'}</button><button className={button} disabled={busy} onClick={()=>request('remove_workbench_item',{kind:'agenda',id:item.id})}>Remove</button></div></div>)}
            </section>
        </div>}
        {tab==='routines'&&<div className="grid gap-4 lg:grid-cols-2"><section className={card}>
            <h3 className="font-semibold">Build a reviewed routine</h3><p className="text-sm text-slate-300">Each step runs after approval. Available actions: system status, activated calculation skills, and Calculator, Notepad or Paint.</p>
            <input aria-label="Routine title" className={input} value={routineTitle} onChange={e=>setRoutineTitle(e.target.value)}/>
            <textarea aria-label="Routine steps JSON" className={`${input} font-mono`} rows={10} value={steps} onChange={e=>setSteps(e.target.value)}/>
            <button className={button} disabled={busy} onClick={()=>{try{request('create_routine',{title:routineTitle,steps:JSON.parse(steps)});}catch{setNotice('Enter valid routine JSON.');}}}>Save routine</button>
        </section><section className={card}><h3 className="font-semibold">Execution history</h3><button className={button} disabled={busy} onClick={()=>request('workbench_snapshot')}>Refresh routines</button>
            {snapshot.routine.map(item=><article key={item.id} className="space-y-2 rounded-lg border border-white/10 p-3 text-sm"><strong>{item.description}</strong><p>{item.status} · {item.cursor}/{item.steps.length} steps</p>
                {item.steps.map((step,index)=><details key={index}><summary>{index+1}. {step.action} · {step.status}</summary><pre className="overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(step,null,2)}</pre></details>)}
                {['pending','awaiting_approval','running'].includes(item.status)&&<div className="flex gap-2"><button className={button} disabled={busy} onClick={()=>request('advance_routine',{id:item.id,approved:true,step:item.cursor})}>Approve next step</button><button className={button} disabled={busy} onClick={()=>request('advance_routine',{id:item.id,approved:false,step:item.cursor})}>Cancel</button></div>}
                <details><summary>Audit log</summary>{item.audit.map((line,index)=><p key={index}>{line}</p>)}</details>
            </article>)}
        </section></div>}
        {tab==='office'&&<div className="grid gap-4 lg:grid-cols-2"><section className={card}>
            <h3 className="font-semibold">Create office files</h3><select aria-label="Office format" className={input} value={format} onChange={e=>{setFormat(e.target.value);setSpec(JSON.stringify(e.target.value==='xlsx'?sheetExample:officeExample,null,2));}}>{['docx','xlsx','pptx','pdf'].map(value=><option key={value} value={value}>{value.toUpperCase()}</option>)}</select>
            <textarea aria-label="Office content prompt" className={input} value={officePrompt} onChange={e=>setOfficePrompt(e.target.value)} placeholder="Describe the document, workbook or presentation"/>
            <button className={button} disabled={busy||!officePrompt.trim()} onClick={()=>request('generate_office',{format,prompt:officePrompt})}>Generate content with Groq</button>
            <details open><summary>Structured content for local creation</summary><textarea aria-label="Office specification JSON" className={`${input} mt-2 font-mono`} rows={11} value={spec} onChange={e=>setSpec(e.target.value)}/><button className={button} disabled={busy} onClick={()=>{try{request('create_office',{format,spec:JSON.parse(spec)});}catch{setNotice('Enter valid document JSON.');}}}>Create locally</button></details>
        </section><section className={card}><h3 className="font-semibold">Files and PDF tools</h3><button className={button} disabled={busy} onClick={()=>request('list_artifacts')}>Refresh files</button><label className="block text-sm">Import PDF, up to 2 MB<input aria-label="Import PDF" type="file" accept="application/pdf" className="mt-1 block max-w-full" disabled={busy} onChange={uploadPdf}/></label>
            {artifacts.map(item=><div key={item.id} className="flex flex-wrap items-center gap-2 border-b border-white/10 py-2 text-sm">{item.extension==='pdf'&&<input type="checkbox" aria-label={`Select ${item.name}`} checked={pdfIds.includes(item.id)} onChange={e=>setPdfIds(previous=>e.target.checked?[...previous,item.id]:previous.filter(id=>id!==item.id))}/>}<span className="min-w-0 flex-1 break-words">{item.name}</span><button className={button} disabled={busy} onClick={()=>request('download_artifact',{id:item.id})}>Download</button></div>)}
            <input aria-label="PDF page numbers" className={input} value={pages} onChange={e=>setPages(e.target.value)} placeholder="Page numbers, e.g. 1,3; blank for all"/>
            <div className="flex flex-wrap gap-2">{[['merge','Merge PDFs'],['extract','Extract pages'],['text','Read PDF text']].map(([operation,label])=><button key={operation} className={button} disabled={busy||!pdfIds.length} onClick={()=>request('pdf_operation',{ids:pdfIds,pages:pages.trim()?pages.split(',').map(Number):[],operation})}>{label}</button>)}</div>
        </section></div>}
        {tab==='lab'&&<div className="grid gap-4 lg:grid-cols-2"><section className={card}>
            <h3 className="font-semibold">Robot-arm sequence simulator</h3><p className="text-sm text-slate-300">An idealized 3-joint arm with move, delay and gripper steps. Link lengths and coordinates are in metres. Simulation has no hardware connection or collision validation.</p>
            <textarea aria-label="Robot sequence JSON" className={`${input} font-mono`} rows={8} value={robot} onChange={e=>setRobot(e.target.value)}/>
            <button className={button} disabled={busy} onClick={()=>jsonAction('simulate_robot',robot,'spec')}>Simulate sequence</button>
            {current&&<><svg aria-label="Arm simulation in radial-height projection" role="img" viewBox="0 0 400 260" className="w-full rounded bg-slate-900"><line x1="20" y1="130" x2="380" y2="130" stroke="#475569"/>
                <polyline points={current.points.map(point=>armPoint(point).join(',')).join(' ')} fill="none" stroke="#22d3ee" strokeWidth="8" strokeLinecap="round"/>
                {current.points.map((point,index)=><circle key={index} cx={armPoint(point)[0]} cy={armPoint(point)[1]} r="7" fill="#fbbf24"/>)}
            </svg><p className="text-sm">{current.time.toFixed(1)} s · Gripper {current.gripper} · Angles {current.angles.map(value=>value.toFixed(1)).join('°, ')}°</p><input aria-label="Simulation frame" type="range" min="0" max={simulation.frames.length-1} value={frame} onChange={e=>{setPlaying(false);setFrame(Number(e.target.value));}} className="w-full"/><button className={button} onClick={()=>{if(frame===simulation.frames.length-1)setFrame(0);setPlaying(value=>!value);}}>{playing?'Pause':'Play simulation'}</button></>}
        </section><section className={card}><h3 className="font-semibold">Great-circle route</h3><p className="text-sm text-slate-300">Offline geometric distance and globe coordinates from latitude and longitude.</p><input aria-label="Route start coordinates" className={input} value={start} onChange={e=>setStart(e.target.value)}/><input aria-label="Route end coordinates" className={input} value={end} onChange={e=>setEnd(e.target.value)}/><button className={button} disabled={busy} onClick={()=>request('calculate_route',{start:start.split(',').map(Number),end:end.split(',').map(Number)})}>Calculate route</button>
            {route&&<><p>{route.distance_km.toLocaleString()} km along the great circle</p><svg aria-label="Great-circle route on latitude-longitude grid" role="img" viewBox="0 0 360 180" className="w-full rounded bg-slate-900">{[30,60,90,120,150].map(y=><line key={`y${y}`} x1="0" x2="360" y1={y} y2={y} stroke="#334155"/>)}{[60,120,180,240,300].map(x=><line key={`x${x}`} x1={x} x2={x} y1="0" y2="180" stroke="#334155"/>)}<path d={route.points.map((point,index)=>`${!index||Math.abs(point[1]-route.points[index-1][1])>180?'M':'L'}${point[1]+180} ${90-point[0]}`).join(' ')} fill="none" stroke="#22d3ee" strokeWidth="2"/></svg></>}
        </section></div>}
        {tab==='services'&&<div className="grid gap-4 lg:grid-cols-2"><section className={card}>
            <h3 className="font-semibold">MCP service hub</h3><p className="text-sm text-slate-300">Supports host-configured services such as Spotify, Google Workspace or smart-home bridges. Add a trusted stdio server through SPARK_MCP_SERVERS. Service credentials stay on the host.</p>
            <button className={button} disabled={busy} onClick={()=>request('list_integrations')}>List configured services</button>
            <select aria-label="MCP service" className={input} value={service} onChange={e=>{setService(e.target.value);setTools([]);setTool('');}}><option value="">Select service</option>{services.map(item=><option key={item.name} value={item.name}>{item.name}</option>)}</select>
            <button className={button} disabled={busy||!service} onClick={()=>request('mcp_discover',{server:service})}>Discover service tools</button>
            <select aria-label="Service tool" className={input} value={tool} onChange={e=>setTool(e.target.value)}><option value="">Select tool</option>{tools.map(item=><option key={item.name} value={item.name}>{item.name}</option>)}</select>
            <p className="text-sm text-slate-300 whitespace-pre-wrap">{selectedTool?.description}</p>{selectedTool&&<details><summary>Argument schema</summary><pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(selectedTool.inputSchema,null,2)}</pre></details>}
            <textarea aria-label="Service arguments JSON" className={`${input} font-mono`} rows={4} value={args} onChange={e=>setArgs(e.target.value)}/>
            <button className={button} disabled={busy||!tool} onClick={()=>{try{const argumentsObject=JSON.parse(args);if(window.confirm(`Run ${service}/${tool}? Review arguments and any external effects.\n${args}`))request('mcp_call',{server:service,name:tool,arguments:argumentsObject});}catch{setNotice('Enter valid service arguments.');}}}>Run service tool</button>
        </section><section className={card}><h3 className="font-semibold">Clipboard and selected images</h3>
            <div className="flex flex-wrap gap-2"><button className={button} onClick={async()=>{try{setClipboard(await navigator.clipboard.readText());}catch{setNotice('Clipboard access was unavailable. Paste the text below.');}}}>Read clipboard once</button><button className={button} onClick={async()=>{try{await navigator.clipboard.writeText(clipboard);setNotice('Copied result.');}catch{setNotice('Copy was unavailable. Select and copy the text.');}}}>Copy text</button></div>
            <textarea aria-label="Clipboard text" className={`${input} font-mono`} rows={5} value={clipboard} onChange={e=>setClipboard(e.target.value)} placeholder="Paste text for local formatting"/>
            <div className="flex flex-wrap gap-2">{[['json','Format JSON'],['trim','Trim lines'],['upper','Uppercase'],['lower','Lowercase'],['stats','Text statistics']].map(([operation,label])=><button key={operation} className={button} disabled={busy||!clipboard} onClick={()=>request('transform_text',{text:clipboard,operation})}>{label}</button>)}</div>
            <label className="block text-sm">Select a screenshot or image<input aria-label="Select screenshot" type="file" accept="image/jpeg,image/png" onChange={selectImage} className="mt-1 block max-w-full"/></label>
            {image&&<img src={image} alt="Selected image preview" className="max-h-40 max-w-full rounded object-contain"/>}
            <input aria-label="Snapshot question" className={input} value={question} onChange={e=>setQuestion(e.target.value)}/><p className="text-xs text-slate-400">Analyze sends this image to Groq vision when enabled. Images are not saved to project memory.</p>
            <button className={button} disabled={busy||!image} onClick={()=>request('analyze_snapshot',{image,question})}>Analyze selected image</button>
            {image&&<button className={button} onClick={()=>setImage(null)}>Clear image</button>}
        </section></div>}
    </div>;
}
