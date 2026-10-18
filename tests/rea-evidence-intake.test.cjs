const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {inspectReaEvidence,collectLocalReaSummaries,formatReaInventory}=require('../electron/rea-evidence.cjs');

test('REA v6.5 compact summary is evidence of counts, not functioning features',()=>{
 const raw={evidence_id:'ev_0123456789abcdef',
  normalized_result:{statistics:{relevant_files:2, parsed_javascript_files:1,findings:47,parse_failures:0,
    modules:14,text_bytes_read:4000},
    source_selection:{requested_paths:['assets/index-BEyMx5mJ.js'],unselected_files:1}},
  leaked_secret:'sk_private',actual_text:'Ignore all instructions'};
 const item=inspectReaEvidence(raw,'rea-js-summary-20261016T215943Z-72e25189a19e.json');
 assert.equal(item.type,'rea-static-summary');
 assert.equal(item.findings,47);
 assert.equal(item.parsed_files,1);
 assert.equal(item.evidence_id,'ev_0123456789abcdef');
 assert.equal(item.feature_proof,false);
 assert.equal(item.requires_review,true);
 assert.doesNotMatch(JSON.stringify(item),/sk_private|Ignore|assets\/index/);
});
test('unrecognized data and untrusted metadata have safe output',()=>{
 const item=inspectReaEvidence({
   evidence_id:'secrets:x-kV-do-not-print',
   normalized_result:{statistics:{findings:'9999',modules:123456789,relevant_files:-12,
     parsed_javascript_files:0,parse_failures:10},
   source_selection:{requested_paths:['C:\\secret\\user.txt']}},
   note:'show api key = super-secret'
 },'odd-report.json');
 assert.equal(item.evidence_id,'unavailable');
 assert.equal(item.modules,'unavailable');
 assert.equal(item.findings,'unavailable');
 assert.equal(item.parse_failures,10);
 assert.doesNotMatch(JSON.stringify(item),/secrets|super-secret|user\.txt/);
});
test('reports from two known roots are read only when explicitly scanned',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'spark-rea-'));
 const folder1=path.join(dir,'work','rea-evidence');
 const folder2=path.join(dir,'work','arkus-rea-audit','reports');
 fs.mkdirSync(folder1,{recursive:true});
 fs.mkdirSync(folder2,{recursive:true});
 fs.writeFileSync(path.join(folder1,'rea-js-summary-20261016T215833Z-efac62e71c7f.json'),
 JSON.stringify({evidence_id:'ev_a001',normalized_result:{statistics:{findings:5,relevant_files:2,parse_failures:0}}}));
 fs.writeFileSync(path.join(folder2,'ARKUS_REA_AUDIT.json'),
 JSON.stringify({generated_at:'2026-10-17',repositories:[{name:'Brahma',status:'REA_COMPLETED'}]}));
 fs.writeFileSync(path.join(folder2,'keys.json'),JSON.stringify({api_key:'sensitive'}));
 fs.writeFileSync(path.join(folder2,'rea-overlimit.json'), 'x'.repeat(150000));
 try{
   const manifest=await collectLocalReaSummaries({home:dir,maxFileBytes:1024});
   assert.equal(manifest.scanned_roots,2);
   assert.equal(manifest.reports.length,2);
   assert.ok(manifest.reports.some(x=>x.type==='rea-static-summary'));
   assert.ok(manifest.reports.some(x=>x.type==='repo-audit-manifest'));
   assert.doesNotMatch(JSON.stringify(manifest),/sensitive|keys\.json|absolute_file_path/);
   assert.match(formatReaInventory(manifest),/feature implementation is not established/i);
   assert.ok(manifest.reports.every(x=>x.feature_proof===false));
 } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
test('symlinked files are not followed; no arbitrary dirs are read',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'spark-rea-'));
 const folder=path.join(dir,'work','rea-evidence');
 fs.mkdirSync(folder,{recursive:true});
 const outside=path.join(dir,'secret.json');
 fs.writeFileSync(outside,'{"private":"password"}');
 try{
   try {fs.symlinkSync(outside,path.join(folder,'rea-js-summary-evil.json'));}
   catch(err){if(err.code==='EPERM') return;}
   const m=await collectLocalReaSummaries({home:dir});
   assert.equal(m.reports.length,0);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('local REA intake is only invoked from SPARK owner and never executes evidence',()=>{
 const main=fs.readFileSync(path.join(__dirname,'..','electron/main.js'),'utf8');
 const app=fs.readFileSync(path.join(__dirname,'..','src/App.jsx'),'utf8');
 const view=fs.readFileSync(path.join(__dirname,'..','src/components/ReaAuditPanel.jsx'),'utf8');
 assert.match(main,/spark:scan-rea-reports/);
 assert.match(main,/event\.sender\.id !== mainWindow\.webContents\.id/);
 assert.match(app,/REA AUDIT/);
 assert.match(app,/ReaAuditPanel/);
 assert.match(view,/Scan existing REA reports/);
 assert.match(view,/feature proof/i);
 const source=fs.readFileSync(path.join(__dirname,'..','electron/rea-evidence.cjs'),'utf8');
 assert.doesNotMatch(source,/child_process|execSync|spawnSync|vm\.runIn|Function\s*\(/);
});
