import React, {useEffect, useRef, useState} from 'react';

const button = 'rounded-lg border border-cyan-500/40 bg-slate-900 px-3 py-2 text-sm font-medium text-cyan-100 hover:border-cyan-300 disabled:opacity-40';
const labels = {'gmail':'Gmail', 'google-calendar':'Google Calendar', 'google-drive':'Google Drive'};
const safeLink = value => {
    if(typeof value !== 'string')return null;
    try{
        const parsed=new URL(value);
        return parsed.protocol==='https:' && (parsed.hostname==='google.com' || parsed.hostname.endsWith('.google.com'))
            ? value : null;
    }catch{return null;}
};
const timestamp = value => {
    if(!value)return 'Never';
    try{return new Date(value*1000).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'});}
    catch{return 'Unavailable';}
};
function SourceLink({url,children}){
    const href=safeLink(url);
    return href?<a href={href} target="_blank" rel="noopener noreferrer" className="text-cyan-200 underline underline-offset-2 hover:text-white">{children}</a>
        :<span className="text-slate-300">{children}</span>;
}

export default function ExecutiveBriefingPanel({socket}){
    const [brief,setBrief]=useState(null),[notice,setNotice]=useState('Read-only briefing is waiting for the first verified pull.');
    const counter=useRef(0),pending=useRef(new Set());
    useEffect(()=>{
        if(!socket)return undefined;
        function pull(){
            if(!socket.connected)return;
            const id='brief-'+Date.now()+'-'+(++counter.current);
            pending.current.add(id);
            socket.emit('integration_sync_action',{request_id:id,workspace_token:socket.workspaceToken,action:'sync_briefing',payload:{}});
        }
        function receive(data){
            if(!pending.current.has(data?.request_id))return;
            pending.current.delete(data.request_id);
            if(!data.ok){setNotice(data.message||'Cannot read local Google snapshots.');return;}
            setBrief(data.result);
            setNotice('Source-linked results from verified local snapshots; not a live inbox connection.');
        }
        socket.on('integration_sync_result',receive);
        socket.on('connect',pull);
        pull();
        const timer=setInterval(pull,15000);
        return()=>{socket.off('integration_sync_result',receive);socket.off('connect',pull);clearInterval(timer);pending.current.clear();};
    },[socket]);

    function refresh(){
        if(!socket?.connected){setNotice('Connect the local SPARK backend first.');return;}
        setNotice('Refresh requested. Google source reads may take time; results remain labeled with the last successful pull.');
        const id='brief-refresh-'+Date.now()+'-'+(++counter.current);
        // Refresh is async in the backend. The regular poll displays its result.
        socket.emit('integration_sync_action',{request_id:id,workspace_token:socket.workspaceToken,action:'sync_now',payload:{}});
    }
    const emails=Array.isArray(brief?.emails)?brief.emails:[];
    const events=Array.isArray(brief?.events)?brief.events:[];
    const documents=Array.isArray(brief?.documents)?brief.documents:[];
    const attention=emails.filter(item=>['urgent','action'].includes(item.priority));
    const rest=emails.filter(item=>!['urgent','action'].includes(item.priority));
    const dueDocs=documents.filter(item=>item.review_candidate);
    return <section className="space-y-4 rounded-xl border border-cyan-400/30 bg-slate-950/70 p-4 text-slate-100" aria-label="Executive briefing">
        <header className="flex flex-wrap items-center justify-between gap-3">
            <div><p className="text-xs uppercase tracking-widest text-cyan-300">SPARK · Executive assistant</p>
                <h3 className="text-xl font-semibold">Needs Attention</h3>
                <p className="mt-1 text-sm text-slate-300">Gmail, Calendar and Drive · India time · source-grounded, read-only</p></div>
            <button type="button" className={button} onClick={refresh}>Refresh source data</button>
        </header>
        <p className="text-sm text-slate-300" role="status">{notice}</p>
        {!brief?<p className="text-sm text-amber-200">No briefing data yet. Connect authorized Google readers and refresh.</p>:<>
            <div className="flex flex-wrap gap-2 text-sm">
                <span className="rounded-lg border border-white/20 px-3 py-2">{attention.length} possible email actions</span>
                <span className="rounded-lg border border-white/20 px-3 py-2">{events.length} scheduled events</span>
                <span className="rounded-lg border border-white/20 px-3 py-2">{dueDocs.length} document review candidates</span>
            </div>
            <div className="grid gap-2 md:grid-cols-3">
                {Object.entries(labels).map(([key,title])=>{
                    const info=brief.sources?.[key]||{};
                    return <div key={key} className="rounded-lg border border-white/15 bg-black/20 p-3">
                        <strong className="block text-sm">{title}</strong>
                        <span className={info.state==='current'&&!info.stale?'text-emerald-300':'text-amber-200'}>
                            {info.state||'not verified'}{info.stale?' · stale':''}</span>
                        <p className="mt-1 text-xs text-slate-300">Last verified: {timestamp(info.last_success)}</p>
                        {info.message&&<p className="mt-1 text-xs text-amber-200">{info.message}</p>}
                        {info.error&&<p className="mt-1 text-xs text-amber-200">{info.error}</p>}
                        {info.possibly_truncated&&<p className="mt-1 text-xs text-amber-200">Bounded sample; more items may exist.</p>}
                    </div>;
                })}
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
                <section className="space-y-2 rounded-lg border border-white/15 p-3">
                    <h4 className="font-semibold text-cyan-100">Important mail candidates ({attention.length})</h4>
                    {attention.length===0?<p className="text-sm text-slate-400">No urgent or action-related messages in the retrieved sample. Check Gmail source status.</p>:
                        attention.slice(0,15).map(item=><article key={item.id} className="border-t border-white/10 pt-2">
                            <p className="text-sm font-semibold"><SourceLink url={item.url}>{item.subject}</SourceLink>
                                {item.unread&&<span className="ml-2 text-xs text-cyan-300">Unread</span>}</p>
                            <p className="break-words text-xs text-slate-300">{item.from}</p>
                            <p className="mt-1 text-sm text-slate-200">{item.snippet}</p>
                            <p className="mt-1 text-xs text-amber-200">{item.reason}</p>
                        </article>)}
                    {rest.length>0&&<details><summary className="cursor-pointer text-sm text-slate-300">Show {rest.length} other messages</summary>
                        {rest.map(item=><p className="border-t border-white/10 py-2 text-sm" key={item.id}><SourceLink url={item.url}>{item.subject}</SourceLink>{item.unread?' · unread':''}</p>)}
                    </details>}
                    <p className="text-xs text-slate-400">Message previews are heuristic. Whether a reply is outstanding is not yet verified.</p>
                </section>
                <div className="space-y-4">
                    <section className="space-y-2 rounded-lg border border-white/15 p-3">
                        <h4 className="font-semibold text-cyan-100">Calendar · Today and tomorrow</h4>
                        {events.length===0?<p className="text-sm text-slate-400">No events in the retrieved window, or Calendar has not been verified.</p>:
                            events.slice(0,15).map(item=><article key={item.id} className="border-t border-white/10 pt-2 text-sm">
                                <SourceLink url={item.url}>{item.title}</SourceLink>
                                <p className="text-xs text-slate-300">{item.start}{item.all_day?' · all day':''}</p>
                                {item.overlap&&<p className="text-xs text-amber-200">Possible time overlap — check event details</p>}
                            </article>)}
                    </section>
                    <section className="space-y-2 rounded-lg border border-white/15 p-3">
                        <h4 className="font-semibold text-cyan-100">Drive · Possible reviews</h4>
                        {dueDocs.length===0?<p className="text-sm text-slate-400">No named review candidates in the retrieved sample, or Drive has not been verified.</p>:
                            dueDocs.slice(0,12).map(item=><article key={item.id} className="border-t border-white/10 pt-2 text-sm">
                                <SourceLink url={item.url}>{item.name}</SourceLink>
                                <p className="text-xs text-slate-400">Modified: {item.modified||'Unknown'} · Review status unconfirmed</p>
                            </article>)}
                    </section>
                </div>
            </div>
            <p className="text-xs text-slate-400">Read-only local cache generated {timestamp(brief.generated_at)}. Missing permissions, stale data and incomplete samples are reported rather than hidden.</p>
        </>}
    </section>;
}
