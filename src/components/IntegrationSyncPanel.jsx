import React,{useEffect,useRef,useState} from 'react';

const button='rounded-lg border border-cyan-500/40 px-3 py-2 text-sm text-cyan-100 disabled:opacity-40';
const time=value=>value?new Date(value*1000).toLocaleString():'Not yet';

export default function IntegrationSyncPanel({socket}){
    const [status,setStatus]=useState(null),[notice,setNotice]=useState('Loading synchronization status…');
    const [query,setQuery]=useState(''),[hits,setHits]=useState(null),[snapshot,setSnapshot]=useState(null);
    const pending=useRef(new Map()),serial=useRef(0);
    function request(action,payload={}){
        if(!socket?.connected){setNotice('Local backend disconnected.');return;}
        const id=`sync-${Date.now()}-${++serial.current}`;
        const timer=setTimeout(()=>{pending.current.delete(id);setNotice('Sync request timed out. Refresh status to retry.');},15000);
        pending.current.set(id,{action,timer});
        socket.emit('integration_sync_action',{workspace_token:socket.workspaceToken,request_id:id,action,payload});
    }
    useEffect(()=>{
        const listener=data=>{
            const item=pending.current.get(data?.request_id);if(!item)return;
            clearTimeout(item.timer);pending.current.delete(data.request_id);
            if(!data.ok){setNotice(data.message);return;}
            if(item.action==='sync_cached')setSnapshot(data.result);
            else if(item.action==='sync_search')setHits(data.result.results);
            else setStatus(data.result);
            setNotice('Pull-only updates stay on this PC. Existing source limits and release holds apply.');
        };
        const refresh=()=>request('sync_status');
        socket?.on('integration_sync_result',listener);socket?.on('connect',refresh);
        refresh();const interval=setInterval(()=>{if(socket?.connected&&!pending.current.size)refresh();},15000);
        return()=>{clearInterval(interval);socket?.off('integration_sync_result',listener);socket?.off('connect',refresh);
            for(const item of pending.current.values())clearTimeout(item.timer);pending.current.clear();};
    },[socket]);
    return <section className="my-4 space-y-3 rounded-xl border border-cyan-500/30 bg-slate-950/70 p-4" aria-label="Automatic integration synchronization">
        <div><h3 className="font-semibold text-cyan-200">Automatic synchronization</h3>
            <p className="mt-1 text-sm text-slate-400">Connected account snapshots on this PC · Pulls while Spark is open.</p></div>
        <p role="status" className="text-sm text-slate-300">{notice}</p>
        {status&&<>
            <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={status.enabled}
                    onChange={e=>request('sync_configure',{enabled:e.target.checked,interval_seconds:status.interval_seconds})}/>Pull updates automatically</label>
                <label className="text-sm">Every <select aria-label="Synchronization interval" className="rounded border border-slate-600 bg-slate-900 p-2"
                    value={status.interval_seconds} onChange={e=>request('sync_configure',{enabled:status.enabled,interval_seconds:Number(e.target.value)})}>
                    {[60,300,900,1800,3600].map(value=><option key={value} value={value}>{value/60} minutes</option>)}</select></label>
                <button className={button} disabled={status.running} onClick={()=>request('sync_now')}>{status.running?'Pulling updates…':'Refresh now'}</button>
                <button className={button} onClick={()=>request('sync_status')}>Refresh status</button>
                <button className={button} disabled={status.running} onClick={()=>request('sync_knowledge')}>Update connected knowledge</button>
            </div>
            {status.knowledge_bridge&&<p className="text-sm text-cyan-100">{status.knowledge_bridge.error||`${status.knowledge_bridge.records} linked source records in Obsidian; ${status.knowledge_bridge.episodes_staged} episodes staged for Graphiti in project ${status.knowledge_bridge.project}. Use Services → graphiti → refresh_project_graph to extract facts.`}</p>}
            <p className="text-xs text-slate-400">Recent items and reference data within each reader’s limits. Jarvis advisory refreshes at most every 15 minutes. Status-only sources have no data feed. This is not a full account backup.</p>
            <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="text-slate-400"><th className="p-2">Source</th><th className="p-2">State</th><th className="p-2">Last successful pull</th><th className="p-2">Snapshot</th></tr></thead>
                <tbody>{status.sources.map(source=><tr key={source.id} className="border-t border-white/10"><td className="p-2">{source.service}<small className="block text-slate-400">{source.tool} · {source.mode}</small></td>
                    <td className="p-2">{source.state}{source.stale?' · stale':''}<small className="block max-w-xs text-amber-200">{source.error}</small>{source.state==='failed'&&<small className="block text-slate-400">Next retry: {time(source.next_due)}</small>}</td>
                    <td className="p-2">{time(source.last_success)}</td><td className="p-2"><button className={button} disabled={!source.last_success} onClick={()=>request('sync_cached',{id:source.id})}>Inspect v{source.version}</button></td></tr>)}</tbody></table></div>
        </>}
        <form className="flex gap-2" onSubmit={e=>{e.preventDefault();request('sync_search',{query});}}>
            <input aria-label="Search synchronized sources" className="min-w-0 flex-1 rounded border border-slate-600 bg-slate-900 p-2" placeholder="Search pulled notes, references and recent items" value={query} maxLength={200} onChange={e=>setQuery(e.target.value)}/>
            <button className={button} disabled={!query.trim()}>Search cache</button></form>
        {hits&&<div>{hits.length===0?<p className="text-sm text-slate-400">No matches in cached sources.</p>:hits.map(hit=><article key={hit.id} className="border-t border-white/10 py-3"><strong>{hit.service}</strong><p className="break-words text-xs">{hit.snippet}</p><button className={button} onClick={()=>request('sync_cached',{id:hit.id})}>Inspect source</button></article>)}</div>}
        {snapshot&&<details open><summary className="cursor-pointer text-cyan-200">{snapshot.id} · {time(snapshot.last_success)} · source content</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(snapshot.data,null,2)}</pre></details>}
    </section>;
}
