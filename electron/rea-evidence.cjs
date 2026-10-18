'use strict';
/* REA v6.5 read-only local evidence intake.
 * Two previously established roots under the user's home directory only.
 * Never executes REA, JS, Python, source code or report text; no uploads.
 * Statistics represent STATIC INDICATORS, not proof of feature behavior.
 */
const fs=require('node:fs/promises');
const path=require('node:path');

const KNOWN_DIRS=[
 ['REA summaries',['work','rea-evidence']],
 ['ARKUS audit',['work','arkus-rea-audit','reports']]
];
const MAX_FILE_BYTES=8*1024*1024;
const MAX_FILES=64;
const MAX_TOTAL_BYTES=16*1024*1024;
const KNOWN_NAME=/^(?:rea-js-summary-[A-Za-z0-9_.-]+|ARKUS_REA_AUDIT|[A-Za-z0-9_.-]*REA[A-Za-z0-9_.-]*AUDIT)\.json$/i;
const safeInt=value=>Number.isSafeInteger(value)&&value>=0&&value<=10000000?value:'unavailable';
const safeName=s=>typeof s==='string'&&/^[A-Za-z0-9_.-]{1,128}$/.test(s)?s:'unavailable';
const SAFE_STAT_FIELDS={
 relevant_files:'files',
 parsed_javascript_files:'parsed_files',
 parse_failures:'parse_failures',
 findings:'findings',
 modules:'modules',
 nested_asar_containers:'asar_containers'
};
function inspectReaEvidence(input, name='report.json'){
  // Intentionally ignore all arbitrary evidence prose and raw code findings.
  const file=safeName(name);
  const result={file, type:'unsupported',feature_proof:false,requires_review:true,
    evidence_id:'unavailable',files:'unavailable',parsed_files:'unavailable',
    parse_failures:'unavailable',findings:'unavailable',modules:'unavailable',
    asar_containers:'unavailable'};
  if(!input || typeof input!=='object'||Array.isArray(input)) return result;
  const normalized=input.normalized_result;
  const stat=normalized && typeof normalized==='object' && !Array.isArray(normalized)
     ? normalized.statistics : null;
  if(stat && typeof stat==='object' && !Array.isArray(stat)){
    result.type='rea-static-summary';
    if(typeof input.evidence_id==='string' && /^ev_[a-zA-Z0-9]{4,80}$/.test(input.evidence_id))
      result.evidence_id=input.evidence_id;
    for(const [key,out] of Object.entries(SAFE_STAT_FIELDS))
      result[out]=safeInt(stat[key]);
  }else if(Array.isArray(input.repositories) || Array.isArray(input.results) ||
       (file==='ARKUS_REA_AUDIT.json' && Object.keys(input).length)){
    result.type='repo-audit-manifest';
    // Number of listed repositories does not prove implementation or tests.
    const repos=Array.isArray(input.repositories)?input.repositories:
                Array.isArray(input.results)?input.results:[];
    result.files=safeInt(repos.length);
  }
  return result;
}

async function collectLocalReaSummaries({home,maxFileBytes=MAX_FILE_BYTES}={}){
  if(typeof home!=='string'||!home.trim()||!path.isAbsolute(home))
    throw Error('An absolute user home folder must be provided.');
  const reports=[];
  let scanned_roots=0, scanned_files=0, skipped_files=0, total_bytes=0;
  for(const [_label,parts] of KNOWN_DIRS){
    const folder=path.join(home,...parts);
    let dir;
    try{
      const info=await fs.lstat(folder);
      if(!info.isDirectory()||info.isSymbolicLink())continue;
      dir=await fs.opendir(folder);
    }catch(e){if(e.code==='ENOENT')continue;throw Error('Could not inspect local REA folder.');}
    scanned_roots++;
    try{
      for await(const entry of dir){
        if(scanned_files>=MAX_FILES||total_bytes>=MAX_TOTAL_BYTES)break;
        if(!KNOWN_NAME.test(entry.name)||!entry.isFile()||entry.isSymbolicLink())continue;
        try{
          const location=path.join(folder,entry.name);
          const info=await fs.lstat(location);
          if(!info.isFile()||info.isSymbolicLink()||info.size>maxFileBytes ||
             info.size<2||info.size>MAX_TOTAL_BYTES-total_bytes){
            skipped_files++;continue;
          }
          scanned_files++;total_bytes+=info.size;
          const raw=await fs.readFile(location,'utf8');
          const data=JSON.parse(raw);
          const item=inspectReaEvidence(data,entry.name);
          // Unknown JSON shapes are not called evidence.
          if(item.type!=='unsupported')reports.push(item);
          else skipped_files++;
        }catch(_){skipped_files++;}
      }
    }finally{await dir.close().catch(()=>{});}
  }
  reports.sort((a,b)=>a.file.localeCompare(b.file));
  return {type:'spark-rea-static-evidence-intake',version:1,
    source:'opt-in local read-only scan',scanned_roots,scanned_files,skipped_files,
    reports,report_count:reports.length,
    conclusion:'Feature implementation is not established by static REA summaries. Review full source evidence and run functional tests before integration.'};
}
function formatReaInventory(m){
  if(!m||m.type!=='spark-rea-static-evidence-intake')return 'No REA inventory.';
  const lines=['SPARK — REA read-only evidence inventory',
    'Reports found: '+m.report_count+'; known folders inspected: '+m.scanned_roots,
    'Feature implementation is not established by static REA summaries.',
    'No report contents, secrets, executable code or file paths included.',
    ''];
  for(const r of m.reports.slice(0,MAX_FILES)){
    lines.push(r.file+' ['+r.type+']',
      '  evidence: '+r.evidence_id+', relevant files: '+r.files+
      ', parsed JS: '+r.parsed_files+', static findings: '+r.findings+
      ', parse failures: '+r.parse_failures);
  }
  return lines.join('\n').slice(0,16000);
}
module.exports={inspectReaEvidence,collectLocalReaSummaries,formatReaInventory};
