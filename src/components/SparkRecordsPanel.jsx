import React,{useEffect,useState} from 'react';
import {X} from 'lucide-react';

export default function SparkRecordsPanel({onClose,loadRecords}) {
    const [data,setData]=useState(null),[space,setSpace]=useState('vayu'),[query,setQuery]=useState('');
    const [notice,setNotice]=useState('Reading existing local records…'),[busy,setBusy]=useState(false);
    const refresh=async()=>{
        setBusy(true);
        try {
            const result=await loadRecords();setData(result);
            setSpace(previous=>result.spaces.some(s=>s.id===previous&&s.count)?previous:(result.spaces.find(s=>s.count)?.id||previous));
            setNotice(result.scope);
        } catch(error) {setData(null);setNotice(String(error?.message||'Local records could not be read.'));}
        finally {setBusy(false);}
    };
    useEffect(()=>{let active=true;loadRecords().then(result=>{if(!active)return;setData(result);setSpace(result.spaces.find(s=>s.count)?.id||'vayu');setNotice(result.scope);}).catch(error=>{if(active)setNotice(String(error?.message||'Local records could not be read.'));});return()=>{active=false;};},[loadRecords]);
    const records=(data?.records||[]).filter(r=>r.space===space&&[r.title,r.source,r.project,r.kind].join(' ').toLowerCase().includes(query.toLowerCase()));
    return <section role="dialog" aria-modal="true" aria-label="SPARK local records" className="fixed z-[115] inset-4 md:inset-x-[8%] md:inset-y-[8%] overflow-y-auto rounded-xl border border-slate-600 bg-slate-950 p-5 text-slate-100 shadow-2xl" style={{WebkitAppRegion:'no-drag'}}>
        <header className="flex items-start justify-between gap-3"><div><h2 className="text-2xl font-semibold">SPARK</h2><p className="mt-1 text-sm text-slate-400">Your existing local records.</p></div><button type="button" onClick={onClose} aria-label="Close SPARK records"><X size={20}/></button></header>
        <div className="my-5 flex flex-wrap items-center gap-3">
            <label className="text-sm">Workspace <select aria-label="Records workspace" value={space} onChange={e=>setSpace(e.target.value)} className="ml-2 rounded border border-slate-600 bg-slate-900 p-2">{(data?.spaces||[{id:'vayu',label:'VAYU',count:0},{id:'vyndios',label:'VYNDI OS',count:0},{id:'vaos',label:'VAOS',count:0},{id:'personal',label:'Personal',count:0},{id:'unassigned',label:'Unassigned',count:0}]).map(s=><option key={s.id} value={s.id}>{s.label} ({s.count})</option>)}</select></label>
            <input aria-label="Filter local records" type="search" placeholder="Find a record…" value={query} onChange={e=>setQuery(e.target.value)} className="min-w-0 rounded border border-slate-600 bg-slate-900 p-2 text-sm"/>
            <button type="button" disabled={busy} onClick={refresh} className="rounded border border-slate-600 px-3 py-2 text-sm">{busy?'Reading…':'Refresh local records'}</button>
        </div>
        <p role="status" className="mb-4 text-xs leading-relaxed text-slate-400">{notice}</p>
        {data?.warnings?.map(w=><p key={w} role="alert" className="text-sm text-amber-200">{w}</p>)}
        {!records.length?<p className="rounded border border-slate-700 p-5 text-slate-400">No matching saved records in this workspace.</p>:<ul className="divide-y divide-slate-800">{records.map(r=><li key={r.id} className="py-4"><h3 className="break-words font-medium">{r.title}</h3><p className="mt-1 break-words text-xs text-slate-400">{r.source}{r.project?' · '+r.project:''} · {r.kind}{r.status?' · '+r.status:''}{r.date?' · '+r.date:''}</p></li>)}</ul>}
    </section>;
}
