import React,{useState} from 'react';
import {Search,FileText,Copy,X,ShieldCheck} from 'lucide-react';

/* Read-only local evidence intake for previously approved REA outputs.
 * Does not run REA, modify files, install packages, or create skills.
 * Static findings are NEVER classified as completed features.
 */
export default function ReaAuditPanel({onClose,ipcRenderer}){
 const [busy,setBusy]=useState(false);
 const [manifest,setManifest]=useState(null);
 const [notice,setNotice]=useState('');
 async function scan(){
   if(busy)return;
   setBusy(true);setNotice('');
   try{
     const result=await ipcRenderer.invoke('spark:scan-rea-reports');
     setManifest(result);
     setNotice(result.report_count
       ?'Read-only inspection complete. Static evidence needs feature-level review.'
       :'No supported REA JSON reports found in the two known folders.');
   }catch(_){setNotice('Unable to inspect existing local REA report folders.');}
   finally{setBusy(false);}
 }
 async function copy(){
   try{
     await ipcRenderer.invoke('spark:copy-rea-inventory');
     setNotice('Safe REA inventory copied. Paste it into ChatGPT for review.');
   }catch(_){setNotice('Scan available reports before copying inventory.');}
 }
 return (
   <section role="dialog" aria-label="SPARK REA Evidence Audit" aria-modal="false"
    className="fixed z-[110] top-16 right-4 md:right-8 w-[min(95vw,590px)] max-h-[83vh]
    overflow-y-auto bg-slate-950/95 border border-cyan-500/40 rounded-2xl shadow-2xl p-5
    text-slate-100 text-sm backdrop-blur-xl" style={{WebkitAppRegion:'no-drag'}}>
     <div className="flex justify-between items-start gap-3 border-b border-cyan-900 pb-3">
       <div>
         <h2 className="flex items-center gap-2 text-lg font-bold text-cyan-300">
           <Search size={19}/> REA AUDIT
         </h2>
         <p className="text-slate-300 mt-1">Inspect previous REA results, without changing projects or running tools</p>
       </div>
       <button aria-label="Close REA Audit" type="button" onClick={onClose}
         className="p-2 rounded border border-slate-700 hover:bg-slate-800"><X size={18}/></button>
     </div>
     <p className="text-slate-300 mt-4">Known Windows folders (under your user profile):</p>
     <div className="mt-2 space-y-1 font-mono text-xs text-cyan-200 break-all">
       <div>work\rea-evidence</div>
       <div>work\arkus-rea-audit\reports</div>
     </div>
     <p className="text-slate-300 mt-3">
       Static REA counts are evidence of analysis, <strong>not feature proof</strong>.
       Source-level inspection, permission checks and runtime tests remain mandatory
       before an integration can be declared complete.
     </p>
     <div className="flex flex-wrap gap-2 mt-5">
       <button type="button" disabled={busy} onClick={scan}
         className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-800 font-semibold
         hover:bg-cyan-700 disabled:opacity-50">
         <Search size={16}/>{busy?'Reading reports…':'Scan existing REA reports'}
       </button>
       <button type="button" disabled={!manifest?.report_count} onClick={copy}
         className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-600
         font-semibold hover:bg-slate-800 disabled:opacity-50">
         <Copy size={16}/> Copy inventory
       </button>
     </div>
     {notice&&<p role="status" className="mt-3 text-cyan-200">{notice}</p>}
     {manifest&&<div className="mt-4">
       <h3 className="font-semibold text-base text-slate-100">
         {manifest.report_count} supported report(s) found
       </h3>
       <p className="text-xs text-slate-300 mt-1">
         {manifest.scanned_roots} known folders inspected; {manifest.skipped_files} unsupported/oversized files skipped
       </p>
       <div className="mt-3 space-y-2">
       {manifest.reports.map((item,i)=><div key={item.file+'-'+i}
          className="rounded-xl border border-slate-700 bg-slate-900/80 p-3">
         <div className="flex items-center gap-2 text-cyan-200 font-semibold break-all">
           <FileText size={15}/>{item.file}
         </div>
         <div className="mt-1 text-xs text-slate-300">
           {item.type==='rea-static-summary'?'REA static summary':'Repository audit manifest'}
         </div>
         <div className="mt-2 grid grid-cols-3 gap-1 text-xs">
           <div>Files <strong>{item.files}</strong></div>
           <div>JS parsed <strong>{item.parsed_files}</strong></div>
           <div>Findings <strong>{item.findings}</strong></div>
         </div>
         <div className="mt-2 text-xs text-amber-200">Feature proof: not established</div>
       </div>)}
       </div>
     </div>}
     <div className="border-t border-slate-700 mt-5 pt-3 text-xs text-slate-300 flex gap-2">
       <ShieldCheck size={16} className="shrink-0 text-cyan-300"/>
       Analysis stays on this PC. SPARK reads JSON data only and never executes
       captured code or posts files to Gemini, Groq, GitHub, or any server.
       The copied inventory is intentionally redacted.
     </div>
   </section>
 );
}
