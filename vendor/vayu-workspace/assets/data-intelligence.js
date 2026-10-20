/* VAYU source-backed intelligence extension, 2026-10-19.
 * Pure, browser-local analysis of explicitly uploaded records. NEVER connects to a live
 * ERP, attributes operations to agents, authorizes a posting, or treats imported data
 * as signed source-of-truth. No third-party dependencies or network requests. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;if(root)root.VAYU_DATA=api;})(typeof window!=='undefined'?window:null,function(){'use strict';
const esc=s=>String(s??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const norm=s=>String(s??'').toLowerCase().replace(/[^a-z0-9]/g,'');
const MAX_ROWS=20000,MAX_COLS=50,MAX_BYTES=2000000,MAX_SOURCES=12;
const HEADS=Object.freeze({'vyndivybes/vaos':'06bdb059d01b6ea85b985f133db55041ad1f2bbd','vyndivybes/vyndios':'cb4051542b4e94ab583153c18022ef51f32ea2eb','vyndivybes/vyndi-design-studio':'41d93b6f5421477b0566197dd4ee581f7d48db3e'});
const reference=(repo,path)=>({repo,path,url:'https://github.com/'+repo+'/blob/'+(HEADS[repo]||'main')+'/'+path});
const V='vyndivybes/vyndios',A='vyndivybes/vaos';
// Source-level evidence is not evidence of live integration, runtime qualification, or correctness.
const CATALOG=[
[1,'Executive KPI dashboard','Strategy','code',A,'apps/web/module-dashboard.mjs','Validate live metrics and completeness'],
[2,'Business performance analysis','Strategy','code',A,'apps/web/business-analytics.mjs','Qualify period-aligned management actuals'],
[3,'Multi-division consolidation','Strategy','partial',V,'src/lib/group-consolidation.ts','Journal attribution and eliminations remain on HOLD'],
[4,'Root-cause investigation','Strategy','partial',A,'apps/web/lib/data-agent-investigation.mjs','Observed discrepancies are not proof of cause'],
[5,'Strategic decision analysis','Strategy','partial',V,'src/lib/decision-intelligence-model.ts','Need approved baseline, scenarios and authority checks'],
[6,'Profit and loss analytics','Finance','code',V,'src/lib/finance/financial-statements.ts','Require complete posted ledger for the requested period'],
[7,'Cash-flow analytics','Finance','code',V,'src/lib/finance/financial-statements.ts','Reconcile funding and cash journals'],
[8,'Budget variance analysis','Finance','partial',V,'src/lib/ibpe-runtime-cash-anchor.test.ts','Require qualified budgets and actual postings'],
[9,'Receivables aging','Finance','code',V,'src/lib/erp-suite-reports.ts','Check invoice and receipt reconciliation'],
[10,'Product costing and pricing','Finance','partial',V,'src/lib/finance/financial-statements.ts','Require actual job costs, overhead basis and priced products'],
[11,'Demand forecasting','Forecasting','partial',V,'src/lib/forecast-learning-model.ts','Minimum qualified closed periods and dated forecasts'],
[12,'Sales forecasting','Forecasting','partial',V,'src/lib/forecast-learning-model.ts','Historical sales records must be qualified'],
[13,'Inventory forecasting','Forecasting','partial',V,'src/lib/erp-suite-reports.ts','Reconcile consumption, balances and future demand'],
[14,'Production capacity analysis','Forecasting','partial',V,'src/lib/advanced-planning-optimizer.ts','Need equipment, routings and availability evidence'],
[15,'Scenario and sensitivity analysis','Forecasting','code',V,'src/lib/monte-carlo-model.ts','Scenarios require explicit inputs and assumptions'],
[16,'Digital employee performance','Workforce','code',A,'intelligence/workforce-analytics.mjs','Mission state alone is not proof of worker execution'],
[17,'Task and workflow analytics','Workforce','code',A,'apps/web/workforce-analytics.mjs','Qualify source missions and completed work'],
[18,'SLA and productivity analysis','Workforce','partial',A,'intelligence/workforce-analytics.mjs','Independent dated SLA and effort evidence required'],
[19,'Procurement analytics','Workforce','code',V,'src/lib/erp-suite-reports.ts','Qualify purchase orders and supplier receipts'],
[20,'Supplier scorecards','Workforce','code',V,'src/lib/supplier-performance-model.ts','Requires complete delivery and quality events'],
[21,'Engineering test analytics','Engineering','partial',V,'src/lib/engineering-release-readiness.test.ts','Qualify measured tests and release evidence'],
[22,'FEA comparison','Engineering','planned',V,'src/lib/engineering-scenario-model.ts','No independently verified FEA results pipeline in inspected source'],
[23,'Quality defects and Pareto','Engineering','partial',V,'src/lib/manufacturing-quality-model.ts','Need complete NCR and CAPA source populations'],
[24,'Composite material analysis','Engineering','partial',V,'src/lib/vibpe-toray-material-adapter.ts','Supplier allowables remain subject to validation'],
[25,'Engineering design trade-offs','Engineering','partial',V,'src/lib/engineering-scenario-model.ts','Tie scenarios to qualified design and test revisions'],
[26,'Interactive analytics dashboards','Analytics','code',V,'src/lib/analytics-studio.ts','Browser projections require qualified data inputs'],
[27,'Data quality audit','Analytics','code',A,'intelligence/g3-cross-source-reconciliation.mjs','Fix uncovered source-field and lineage gaps'],
[28,'Reproducible analytical notebooks','Analytics','planned',A,'intelligence/README.md','No notebook execution workflow verified in inspected repo'],
[29,'Automated management reporting','Analytics','partial',A,'apps/web/api/founder-agent-report.mjs','Scheduled execution and report freshness unverified'],
[30,'AI-assisted decision recommendations','Analytics','partial',V,'src/lib/decision-intelligence-model.ts','Recommendations require approved sources; no automatic posting']
].map(([id,name,domain,status,repo,path,gap])=>Object.freeze({id,name,domain,status,evidence:reference(repo,path),gap}));
const OPPORTUNITIES=[['Finance and accounting',15],['CRM and sales',15],['Manufacturing',15],['Supply chain',15],['Autonomous workforce',20],['Engineering and digital twin',20],['Quality and compliance',15],['Predictive and statistical models',15],['Data governance and lineage',15],['Strategy and optimization',15],['Visualization and exploration',15]];
const SOURCES=[
['sales_orders','Sales orders',['sales_order_id','order_id','id']],
['job_cards','Production job cards',['job_card_id','id']],
['purchase_orders','Purchase orders',['purchase_order_id','po_id','id']],
['goods_receipts','Goods receipts',['goods_receipt_id','receipt_id','grn_id','id']],
['sales_invoices','Sales invoices',['sales_invoice_id','invoice_id','id']],
['supplier_invoices','Supplier invoices',['supplier_invoice_id','invoice_id','id']],
['journal_entries','Posted journal lines',['entry_id','line_id','journal_line_id','id']],
['customer_receipts','Customer receipts',['customer_receipt_id','receipt_id','payment_id','id']],
['inventory','Inventory records',['inventory_id','stock_event_id','id']],
['quality','Quality NCR / CAPA',['ncr_id','capa_id','quality_id','id']],
['engineering','Engineering and VEDM',['evidence_id','test_id','revision_id','id']],
['agent_executions','VAOS execution evidence',['execution_id','mission_id','id']],
['other','Other source records',['record_id','id']]
].map(([id,name,keys])=>Object.freeze({id,name,keys}));
// Explicit, typed foreign keys prevent accidental joins on coincidentally equal IDs.
const LINKS=[
['salesOrderId','sales_orders'],['sales_order_id','sales_orders'],['order_id','sales_orders'],
['jobCardId','job_cards'],['job_card_id','job_cards'],
['purchaseOrderId','purchase_orders'],['purchase_order_id','purchase_orders'],['po_id','purchase_orders'],
['goodsReceiptId','goods_receipts'],['goods_receipt_id','goods_receipts'],['grn_id','goods_receipts'],
['salesInvoiceId','sales_invoices'],['sales_invoice_id','sales_invoices'],
['supplierInvoiceId','supplier_invoices'],['supplier_invoice_id','supplier_invoices'],
['ncr_id','quality'],['capa_id','quality'],['execution_id','agent_executions'],
['evidence_id','engineering'],['revision_id','engineering']
].map(([column,type])=>({column:norm(column),type}));
function columns(rows){const out=[];const seen=new Set();for(const r of rows)for(const k of Object.keys(r)){if(!seen.has(k)){out.push(k);seen.add(k)}}return out}
function validateRows(rows){if(!Array.isArray(rows)||!rows.length||rows.length>MAX_ROWS)throw Error('Use 1–20,000 records');
 if(rows.some(r=>!r||typeof r!=='object'||Array.isArray(r)))throw Error('Every record must be an object');
 const cols=columns(rows);if(cols.length>MAX_COLS)throw Error('Maximum 50 unique columns');
 if(cols.some(k=>!k||['__proto__','prototype','constructor'].includes(k)||k.length>160))throw Error('Invalid column name');
 for(const r of rows)for(const x of Object.values(r)){if(x!==null&&typeof x!=='string'&&typeof x!=='number'&&typeof x!=='boolean')throw Error('Only scalar values are supported');}
 return cols;
}
function importRows(type,filename,rows,at=''){const config=SOURCES.find(x=>x.id===type);if(!config)throw Error('Unsupported source category');const cols=validateRows(rows);const key=selectKey(type,cols);const found=key?rows.map(r=>String(r[key]??'').trim()).filter(Boolean):[];const dup=found.length-new Set(found).size;
 return {type,name:config.name,filename:String(filename).slice(0,180),importedAt:at||new Date().toISOString(),rows,cols,key,metrics:{rows:rows.length,missingIds:key?rows.length-found.length:null,duplicateIds:key?dup:null},provenance:'USER_UPLOADED_UNVERIFIED',qualification:'HOLD'};}
function selectKey(type,cols){let source=SOURCES.find(s=>s.id===type);for(const cand of (source?.keys||[])){const k=cols.find(x=>norm(x)===norm(cand));if(k)return k;}return null;}
function parseJSON(s){const data=JSON.parse(s);const rows=Array.isArray(data)?data:data&&Array.isArray(data.rows)?data.rows:null;if(!rows)throw Error('JSON must contain a record array or a top-level rows array');return rows;}
function importText(type,filename,text,parseCSV){if(new TextEncoder().encode(text).byteLength>MAX_BYTES)throw Error('Source maximum is 2 MB');const rows=/\.json$/i.test(filename)?parseJSON(text):/\.csv$/i.test(filename)?parseCSV(text):null;if(!rows)throw Error('Select a .csv or .json file');return importRows(type,filename,rows)}
const nameFor=k=>SOURCES.find(s=>s.id===k)?.name||k;
function exactLink(row,sourceType,targetSource){if(!targetSource.key)return [];
 const wanted=new Set(LINKS.filter(x=>x.type===targetSource.type).map(x=>x.column));
 // Ignore generic id, record id, and primary key of the row's own source.
 const ownKey=selectKey(sourceType,Object.keys(row));const refs=[];
 for(const field of Object.keys(row)){if(field===ownKey||!wanted.has(norm(field)))continue;
  const value=String(row[field]??'').trim();if(!value)continue;
  targetSource.rows.forEach((item,index)=>{if(String(item[targetSource.key]??'').trim()===value)refs.push({field,value,index});});}
 return refs;
}
function traceRecord(sources,sourceIndex,recordIndex){const own=sources[sourceIndex],row=own?.rows[recordIndex];if(!row)return {outgoing:[],incoming:[],unresolved:[]};let outgoing=[],incoming=[],unresolved=[];
 for(let j=0;j<sources.length;j++){
  const target=sources[j];if(target.type!==own.type){const r=exactLink(row,own.type,target);for(const a of r.slice(0,30))outgoing.push({...a,sourceIndex:j,sourceType:target.type});}
  if(j!==sourceIndex&&own.key){const matched=exactLink;for(let i=0;i<target.rows.length;i++){
   const x=target.rows[i];const fields=Object.keys(x).filter(k=>LINKS.some(z=>z.type===own.type&&z.column===norm(k))&&k!==target.key);
   if(fields.some(k=>String(x[k]??'').trim()!==''&&String(x[k]??'').trim()===String(row[own.key]??'').trim())){incoming.push({sourceIndex:j,index:i,sourceType:target.type});if(incoming.length>=50)break;}
  }}
 }
 for(const field of Object.keys(row)){
  const expected=LINKS.find(x=>x.column===norm(field)&&x.type!==own.type);if(!expected||!String(row[field]??'').trim())continue;
  const targets=sources.filter(s=>s.type===expected.type);
  if(!targets.length)unresolved.push({field,reason:'Target source not imported',target:expected.type});
  else if(!targets.some(s=>exactLink(row,own.type,s).some(x=>x.field===field)))unresolved.push({field,reason:'No exact matching target record',target:expected.type});
 }
 return {outgoing:outgoing.slice(0,50),incoming:incoming.slice(0,50),unresolved};}
function assessSourceQuality(sources){
 const all=sources.map((s,i)=>({s,i,keyValues:s.key?new Set(s.rows.map(r=>String(r[s.key]??'').trim()).filter(Boolean)):new Set()}));
 return all.map(({s,i})=>{let verifiedLinks=0,orphanRefs=0,targetsNotImported=0;
  for(const row of s.rows)for(const field of Object.keys(row)){
   if(field===s.key||!String(row[field]??'').trim())continue;
   const ref=LINKS.find(x=>x.column===norm(field)&&x.type!==s.type);if(!ref)continue;
   const targetFiles=all.filter(t=>t.s.type===ref.type&&t.s.key);
   if(!targetFiles.length){targetsNotImported++;continue;}
   if(targetFiles.some(t=>t.keyValues.has(String(row[field]).trim())))verifiedLinks++;else orphanRefs++;
  }
  return {type:s.type,file:s.filename,key:s.key,rows:s.rows.length,missingIds:s.metrics.missingIds,duplicateIds:s.metrics.duplicateIds,exactLinks:verifiedLinks,orphans:orphanRefs,targetsNotImported,authorityStatus:'UNVERIFIED_UPLOAD'};
 });
}
function statusText(s){return({code:'Code evidenced',partial:'Partial / qualified data needed',planned:'Not verified in code'})[s]||s;}
function badge(status){return `<span class="vdi-badge vdi-${esc(status)}">${esc(statusText(status))}</span>`;}
const card=(title,inner,note='')=>`<section class="acard"><h2>${esc(title)}</h2>${note?`<p class="anote">${esc(note)}</p>`:''}${inner}</section>`;
const note=txt=>`<p class="anote">${esc(txt)}</p>`;
const options=(values,chosen)=>values.map(([v,t])=>`<option value="${esc(v)}" ${v===chosen?'selected':''}>${esc(t)}</option>`).join('');
const repoLink=x=>x?`<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.repo)} / ${esc(x.path)}</a>`:'Not verified';
function model(st){if(!st.enterprise)st.enterprise={sources:[],type:'sales_orders',sourceIndex:0,recordIndex:null,search:'',category:'all',status:'all',selectedCapability:1,pagination:0,message:''};return st.enterprise;}
function capabilities(e){const counts=Object.fromEntries(['code','partial','planned'].map(s=>[s,CATALOG.filter(c=>c.status===s).length]));
 const items=CATALOG.filter(c=>(e.category==='all'||e.category===c.domain)&&(e.status==='all'||e.status===c.status));
 const c=CATALOG.find(x=>x.id===e.selectedCapability)||CATALOG[0];
 return `<div class="vdi-kpis"><div><strong>30</strong><span>Audited use cases</span></div><div><strong>${counts.code}</strong><span>Code evidenced</span></div><div><strong>${counts.partial}</strong><span>Partial / qualified input</span></div><div><strong>${counts.planned}</strong><span>Unverified</span></div></div>`+
 note('Read-only code evidence captured 19 Oct 2026. "Code evidenced" never means deployed, source-connected or production-qualified.')+
 `<div class="vdi-split"><section class="acard"><h2>Capability register</h2><div class="vdi-controls"><label>Domain<select id="vdiDomain">${options([['all','All domains'],...new Set(CATALOG.map(x=>x.domain))].map(x=>Array.isArray(x)?x:[x,x]),e.category)}</select></label><label>Evidence status<select id="vdiStatus">${options([['all','All statuses'],['code','Code evidenced'],['partial','Partial'],['planned','Not verified']],e.status)}</select></label></div><div class="vdi-scroll" role="list">${items.map(c=>`<button type="button" class="vdi-cap ${c.id===c.id&&c.id===e.selectedCapability?'chosen':''}" data-vdi-cap="${c.id}"><span>${c.id}. ${esc(c.name)}</span>${badge(c.status)}</button>`).join('')||'<p>No matching capabilities.</p>'}</div></section>`+
 `<section class="acard"><h2>${esc(c.id+'. '+c.name)}</h2>${badge(c.status)}<p><b>Domain:</b> ${esc(c.domain)}</p><p><b>Code evidence:</b> ${repoLink(c.evidence)}</p><p><b>Closure requirement:</b> ${esc(c.gap)}</p><p><b>Acceptance:</b> inspect the source, run relevant tests, verify live authorized readback, confirm period completeness and prove an end-to-end record trace.</p><p class="anote">Evidence is pinned to an inspected commit. Review newer commits separately; this tool never fetches GitHub automatically.</p></section></div>`+
 card('Additional analysis opportunity catalogue',`<p>${OPPORTUNITIES.reduce((n,x)=>n+x[1],0)} additional proposed use cases in 11 families, beyond the 30 audited use cases. These are <b>opportunities, not installed features</b>.</p><div class="vdi-opportunities">${OPPORTUNITIES.map(([label,count])=>`<div><span>${esc(label)}</span><b>${count}</b></div>`).join('')}</div>`)+
 card('Evidence and source architecture',`<ol><li>VYNDI OS owns canonical finance, CRM, inventory, production and engineering records.</li><li>VAOS owns governed agent execution and workforce evidence.</li><li>This workspace reads only locally supplied snapshots: no hidden credentials, posting, or background syncing.</li><li>Use <b>Source intake</b> to import authorized records, then <b>Ledger trace</b> to inspect exact record links.</li><li>Qualified KPI totals and legal/statutory reports must still be calculated by the authoritative system.</li></ol>`);
}
function coverage(e){const ss=e.sources||[],qa=assessSourceQuality(ss);const expected=['sales_orders','job_cards','purchase_orders','goods_receipts','sales_invoices','supplier_invoices','journal_entries','customer_receipts','inventory','quality','engineering','agent_executions'];
 return `<div class="vdi-kpis"><div><strong>${ss.length}</strong><span>Imported files</span></div><div><strong>${ss.reduce((n,s)=>n+s.rows.length,0)}</strong><span>Imported rows</span></div><div><strong>${new Set(ss.map(s=>s.type)).size}/${expected.length}</strong><span>Source families available</span></div><div><strong>0</strong><span>Signed, verified connectors</span></div></div>`+
 card('Source qualification',note('All uploads are user-provided, unverified and session-only. A filename or column label does not prove authority, completeness, statutory validity or an agent execution.')+
 `<div class="vdi-controls"><label>Record type<select id="vdiUploadType">${options(SOURCES.map(s=>[s.id,s.name]),e.type)}</select></label><label>Upload CSV or JSON (max 2 MB)<input type="file" accept=".csv,.json,text/csv,application/json" id="vdiUpload"></label><button id="vdiExportManifest">Export manifest</button></div><p id="vdiMessage" role="status" class="anote">${esc(e.message||'No network sync or credentials required.')}</p>`)+
 card('Imported source coverage',`<div class="atable"><table><thead><tr><th>Record family</th><th>Rows</th><th>Primary key</th><th>Missing IDs</th><th>Repeated IDs</th><th>Exact references</th><th>Orphan references</th><th>Missing source family</th><th>Provenance</th><th></th></tr></thead><tbody>${ss.map((s,i)=>`<tr><td>${esc(s.name)}<small class="vdi-mini">${esc(s.filename)}</small></td><td>${s.rows.length}</td><td>${esc(s.key||'Unknown')}</td><td>${s.metrics.missingIds??'Not checked'}</td><td>${s.metrics.duplicateIds??'Not checked'}</td><td>${qa[i].exactLinks}</td><td>${qa[i].orphans}</td><td>${qa[i].targetsNotImported}</td><td>Uploaded; qualification HOLD</td><td><button data-vdi-remove="${i}">Remove</button></td></tr>`).join('')||'<tr><td colspan="10">No imported source data. Use your system exports or a CSV/JSON file to begin.</td></tr>'}</tbody></table></div>`)+
 card('Cross-source integrity',`<p><b>${qa.reduce((n,r)=>n+r.exactLinks,0)}</b> exact foreign-key matches · <b>${qa.reduce((n,r)=>n+r.orphans,0)}</b> references with no matching imported target · <b>${qa.reduce((n,r)=>n+r.targetsNotImported,0)}</b> references whose source family is missing.</p>`,'These are structural checks on manually imported data. They do not qualify financial statements, historical completeness, or operational truth.')+
 card('Operational source families still unavailable',`<div class="vdi-tags">${expected.filter(type=>!ss.some(s=>s.type===type)).map(type=>`<span>${esc(nameFor(type))}</span>`).join('')||'All twelve listed record families have at least one uploaded file. They are still unverified until independently qualified.'}</div>`,'Source coverage is not record, period, or authority coverage.');
}
function cellPreview(r,k){const s=String(r[k]??'');return s.length>90?s.slice(0,90)+'…':s;}
function ledger(e){const ss=e.sources||[];if(!ss.length)return card('Ledger and digital-thread explorer',note('No imported files. Open Source intake and upload your own CSV/JSON exports. Real ledger records cannot be inferred from the knowledge graph.'));
 if(e.sourceIndex>=ss.length)e.sourceIndex=0;const s=ss[e.sourceIndex];const q=e.search.toLowerCase(),subset=s.rows.map((row,i)=>({row,i})).filter(x=>!q||Object.values(x.row).some(v=>String(v??'').toLowerCase().includes(q)));const first=Math.max(0,Math.min(e.pagination,Math.max(0,subset.length-1)));const view=subset.slice(first,first+40);
 const keys=s.cols.slice(0,5),selection=e.recordIndex===null?null:s.rows[e.recordIndex];
 let body=card('Ledger trace • uploaded evidence',`<p class="anote">Exact-key record navigation across separately imported source families. A connection is shown only when an explicit foreign-key field matches a target source ID. This does <b>not</b> prove accounting reconciliation or a complete provenance chain.</p><div class="vdi-controls"><label>Source file<select id="vdiCurrentSource">${options(ss.map((x,i)=>[String(i),x.name+' · '+x.filename]),String(e.sourceIndex))}</select></label><label>Find source record<input id="vdiSearch" type="search" placeholder="ID, status, reference…" value="${esc(e.search)}"></label><button id="vdiSearchGo">Search</button><button id="vdiExportRows">Export selected source JSON</button></div><p class="anote">${subset.length} matching of ${s.rows.length} · primary key ${esc(s.key||'not identified')} · source: manually uploaded / unverified</p><div class="atable"><table><thead><tr>${keys.map(k=>`<th>${esc(k)}</th>`).join('')}<th>Trace</th></tr></thead><tbody>${view.map(({row,i})=>`<tr>${keys.map(k=>`<td title="${esc(row[k])}">${esc(cellPreview(row,k))}</td>`).join('')}<td><button data-vdi-row="${i}">Inspect</button></td></tr>`).join('')||`<tr><td colspan="${keys.length+1}">No matching records</td></tr>`}</tbody></table></div><div class="wactions"><button id="vdiPrev" ${first===0?'disabled':''}>Previous 40</button><span>${subset.length?first+1:0}–${Math.min(first+40,subset.length)} of ${subset.length}</span><button id="vdiNext" ${first+40>=subset.length?'disabled':''}>Next 40</button></div>`);
 if(selection){const t=traceRecord(ss,e.sourceIndex,e.recordIndex);const attrs=Object.entries(selection).map(([k,v])=>`<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join('');
 const link=(rel,mode)=>`<button data-vdi-jump="${rel.sourceIndex}:${mode==='outgoing'?rel.index:rel.index}">${esc(nameFor(rel.sourceType))} · ${esc(mode==='outgoing'?rel.field:'matching reference')}${mode==='outgoing'?' → '+esc(rel.value):''}</button>`;
 body+=`<div class="vdi-split">${card('Inspected source row '+(e.recordIndex+1),`<p class="anote">${esc(s.filename)} · no authority qualification inferred</p><div class="atable"><table><tbody>${attrs}</tbody></table></div>`)}${card('Related records',`<h3>Outgoing exact links (${t.outgoing.length})</h3><div class="vdi-rel">${t.outgoing.map(x=>link(x,'outgoing')).join('')||'No proven outgoing links in imported sources.'}</div><h3>Incoming exact links (${t.incoming.length})</h3><div class="vdi-rel">${t.incoming.map(x=>link(x,'incoming')).join('')||'No proven incoming links in imported sources.'}</div><h3>Unresolved references (${t.unresolved.length})</h3>${t.unresolved.map(x=>`<p class="anote">${esc(x.field)} → ${esc(x.target)}: ${esc(x.reason)}</p>`).join('')||note('No unresolved references found by the known field-name rules. This does not imply a complete trace.')}`)}</div>`;
 }
 return body;}
function render(tab,st){const e=model(st);if(tab==='catalog')return capabilities(e);if(tab==='sources')return coverage(e);if(tab==='ledger')return ledger(e);return '';}
function bind(host,st,rerender,parseCSV,download){const e=model(st);const one=id=>host.querySelector('#'+id);
 one('vdiDomain')?.addEventListener('change',x=>{e.category=x.target.value;rerender()});one('vdiStatus')?.addEventListener('change',x=>{e.status=x.target.value;rerender()});
 host.querySelectorAll('[data-vdi-cap]').forEach(x=>x.onclick=()=>{e.selectedCapability=+x.dataset.vdiCap;rerender()});
 one('vdiUploadType')?.addEventListener('change',x=>{e.type=x.target.value});
 one('vdiUpload')?.addEventListener('change',async x=>{try{const f=x.target.files[0];if(!f)return;if(f.size>MAX_BYTES)throw Error('Source file is larger than 2 MB');if(e.sources.length>=MAX_SOURCES)throw Error('Maximum 12 simultaneous source files');const rec=importText(e.type,f.name,await f.text(),parseCSV);e.sources.push(rec);e.message='Imported '+rec.rows.length+' rows from '+rec.filename+'. Qualification HOLD: verify original source.';e.recordIndex=null;e.sourceIndex=e.sources.length-1;rerender();}catch(err){e.message=String(err.message||err);const el=one('vdiMessage');if(el)el.textContent=e.message}});
 host.querySelectorAll('[data-vdi-remove]').forEach(x=>x.onclick=()=>{e.sources.splice(+x.dataset.vdiRemove,1);e.sourceIndex=0;e.recordIndex=null;e.pagination=0;e.message='Session import removed; original file was not changed.';rerender()});
 one('vdiExportManifest')?.addEventListener('click',()=>{const manifest={format:'vayu-source-coverage-v1',generatedAt:new Date().toISOString(),qualification:'UNVERIFIED_UPLOAD',sources:e.sources.map(({rows,...meta})=>meta)};download(JSON.stringify(manifest,null,2),'VAYU-source-coverage.json','application/json')});
 one('vdiCurrentSource')?.addEventListener('change',x=>{e.sourceIndex=+x.target.value;e.recordIndex=null;e.pagination=0;e.search='';rerender()});
 one('vdiSearchGo')?.addEventListener('click',()=>{e.search=one('vdiSearch').value;e.pagination=0;e.recordIndex=null;rerender()});
 one('vdiSearch')?.addEventListener('keydown',x=>{if(x.key==='Enter'){e.search=x.target.value;e.pagination=0;e.recordIndex=null;rerender()}});
 one('vdiPrev')?.addEventListener('click',()=>{e.pagination=Math.max(0,e.pagination-40);rerender()});one('vdiNext')?.addEventListener('click',()=>{e.pagination+=40;rerender()});
 host.querySelectorAll('[data-vdi-row]').forEach(x=>x.onclick=()=>{e.recordIndex=+x.dataset.vdiRow;rerender()});
 host.querySelectorAll('[data-vdi-jump]').forEach(x=>x.onclick=()=>{const [a,b]=x.dataset.vdiJump.split(':').map(Number);e.sourceIndex=a;e.recordIndex=b;e.search='';e.pagination=Math.floor(b/40)*40;rerender()});
 one('vdiExportRows')?.addEventListener('click',()=>{const s=e.sources[e.sourceIndex];if(s)download(JSON.stringify({format:'vayu-imported-source-v1',qualification:s.qualification,type:s.type,filename:s.filename,rows:s.rows},null,2),'VAYU-'+s.type+'-records.json','application/json')});
}
return {CATALOG,HEADS,OPPORTUNITIES,SOURCES,MAX_ROWS,MAX_COLS,MAX_BYTES,MAX_SOURCES,selectKey,validateRows,assessSourceQuality,parseJSON,importRows,importText,exactLink,traceRecord,render,bind};
});
