import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import SparkScreens from '../src/components/SparkScreens';
import '../src/index.css';

const listeners = new Map();
window.__repositoryRequests = [];
const evidence = {repository:'C:/reference', sources:[{path:'cache.py',content:'def calculate(x): return x * 2',sha256:'fixture'}], inventory:['cache.py'], skipped:[], limitations:['Static sample only'], inventory_truncated:false};
const report = {...evidence, repository:'example/repo', imported:{url:'https://github.com/example/repo'}, id:'a'.repeat(24), goal:'Improve caching', summary:'Use a bounded cache.', opportunities:[{title:'Bound repeated calculations', rationale:'Retain recent results with a fixed capacity.', evidence:['cache.py'], spark_paths:['backend/calculator.py'], verification:'Cache size stays within capacity.'}]};
let saved = [], candidate;
const socket = {
    connected:true, workspaceToken:'fixture',
    on(event, fn) {if (!listeners.has(event)) listeners.set(event,new Set()); listeners.get(event).add(fn);},
    off(event, fn) {listeners.get(event)?.delete(fn);},
    emit(event, request) {
        window.__repositoryRequests.push(request);
        let result, message;
        if (request.action === 'list_repository_analyses') result = request.project === 'general' ? saved : [];
        if (request.action === 'preview_repository') result = evidence;
        if (request.action === 'analyze_repository') {saved = [report]; result = report;}
        if (request.action === 'read_repository_analysis') result = report;
        if (request.action === 'stage_repository_upgrade') result = candidate = {id:'b'.repeat(24), status:'staged', changes:[{path:'backend/calculator.py',content:'value = 2'}], provenance:{analysis_id:report.id,repository:report.repository,opportunity:report.opportunities[0]}};
        if (request.action === 'list_repair_candidates') result = candidate ? [candidate] : [];
        if (request.action === 'test_repair_candidate') result = candidate = {...candidate, status:'tested'};
        if (request.action === 'import_repository') message = 'Clone timed out; try a smaller repository.';
        setTimeout(() => listeners.get('workspace_result')?.forEach(fn => fn({...request,ok:!message,result,message})), 20);
    }
};
function Harness() {
    const [project,setProject] = useState('general');
    return <main className="min-h-screen bg-slate-950 p-4 text-white">
        <button onClick={() => setProject('other')}>Switch test workspace</button>
        <SparkScreens socket={socket} project={project} initialPage="Repository Intelligence" compactNavigation/>
    </main>;
}
createRoot(document.getElementById('root')).render(<Harness/>);
