import React from 'react';
import {createRoot} from 'react-dom/client';
import EvolutionPanel from '../src/components/EvolutionPanel';
import '../src/index.css';

const listeners = new Map();
window.__evolutionRequests = [];
const report = {id:'a'.repeat(24), repository:'C:/reference', goal:'Improve caching', summary:'The sampled source uses a bounded cache.', sources:[{path:'cache.py',sha256:'fixture',content:'sample evidence'}], skipped:[], inventory_truncated:false, limitations:['Static sample only'], opportunities:[{title:'Bound repeated calculations',rationale:'Retain recent results with a fixed capacity.',evidence:['cache.py'],spark_paths:['backend/calculator.py'],verification:'Repeated inputs return the same result and capacity remains bounded.'}]};
let candidate = null;
const socket = {connected:true, workspaceToken:'fixture', on(event, fn){listeners.set(event,fn);}, off(event){listeners.delete(event);}, emit(event, request){
    window.__evolutionRequests.push(request);
    let result;
    if (request.action === 'analyze_repository' || request.action === 'read_repository_analysis') result = report;
    if (request.action === 'list_repository_analyses') result = [report];
    if (request.action === 'stage_repository_upgrade') result = candidate = {id:'b'.repeat(24),status:'staged',changes:[{path:'backend/calculator.py',content:'value = 2',sha256:'fixture'}],provenance:{analysis_id:report.id,opportunity:report.opportunities[0]}};
    if (request.action === 'test_repair_candidate') result = candidate = {...candidate,status:'tested'};
    if (request.action === 'activate_repair_candidate') result = {id:'c'.repeat(24),status:'applied',restart_required:true};
    if (request.action === 'rollback_repair') result = {id:'c'.repeat(24),status:'rolled_back',restart_required:true};
    setTimeout(() => listeners.get('workspace_result')?.({...request,ok:true,result}),10);
}};
createRoot(document.getElementById('root')).render(<main className="min-h-screen bg-slate-950 p-4 text-white"><EvolutionPanel socket={socket} project="general"/></main>);
