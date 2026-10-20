'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const data=require('../assets/data-intelligence.js');
test('30 reviewed features and 175 scoped opportunities; not 205 installed modules',()=>{
 assert.equal(data.CATALOG.length,30);
 assert.equal(data.OPPORTUNITIES.reduce((n,x)=>n+x[1],0),175);
 assert.equal(data.CATALOG.some(c=>c.status==='planned'),true);
 assert.equal(new Set(data.CATALOG.map(c=>c.id)).size,30);
});
test('repository URLs anchor inspected source revision',()=>{
 for(const c of data.CATALOG){assert.match(c.evidence.url,/^https:\/\/github.com\/vyndivybes\//);assert.ok(c.gap.length>8);assert.match(c.evidence.url,/blob\/[0-9a-f]{40}\//)}
});
test('imported CSV and JSON rows keep provenance HOLD and detect missing/duplicate IDs',()=>{
 const src=data.importRows('sales_orders','export.csv',[{sales_order_id:'SO-1',amount:'250'},{sales_order_id:'SO-1',amount:'300'},{sales_order_id:'',amount:'0'}]);
 assert.equal(src.key,'sales_order_id');assert.equal(src.metrics.duplicateIds,1);assert.equal(src.metrics.missingIds,1);assert.equal(src.qualification,'HOLD');
 const j=data.importText('job_cards','job_cards.json',JSON.stringify({rows:[{jobCardId:'JC-1',sales_order_id:'SO-1'}]}),()=>{throw Error('should not parse CSV')});
 assert.equal(j.key,'jobCardId');assert.equal(j.rows.length,1);
});
test('foreign keys yield only exact matching target records, both directions',()=>{
 const orders=data.importRows('sales_orders','orders.csv',[{sales_order_id:'SO-1',status:'confirmed'},{sales_order_id:'SO-2',status:'hold'}]);
 const jobs=data.importRows('job_cards','jobs.csv',[{job_card_id:'JC-9',sales_order_id:'SO-1'},{job_card_id:'JC-10',sales_order_id:'SO-MISSING'}]);
 let t=data.traceRecord([orders,jobs],1,0);
 assert.deepEqual(t.outgoing.map(x=>[x.sourceIndex,x.index,x.field,x.value]),[[0,0,'sales_order_id','SO-1']]);
 assert.equal(t.unresolved.length,0);
 t=data.traceRecord([orders,jobs],0,0);
 assert.deepEqual(t.incoming.map(x=>[x.sourceIndex,x.index]),[[1,0]]);
 t=data.traceRecord([orders,jobs],1,1);
 assert.equal(t.outgoing.length,0);assert.equal(t.unresolved.length,1);
});
test('source never joins on untyped matching value',()=>{
 const orders=data.importRows('sales_orders','orders.csv',[{sales_order_id:'123',label:'A'}]);
 const jobs=data.importRows('job_cards','jobs.csv',[{job_card_id:'123',memo:'Unrelated number'}]);
 assert.equal(data.traceRecord([orders,jobs],1,0).outgoing.length,0);
 assert.equal(data.traceRecord([orders,jobs],0,0).incoming.length,0);
});
test('malformed data rejected without imports',()=>{
 assert.throws(()=>data.importRows('sales_orders','bad',[]),/1–20,000/);
 assert.throws(()=>data.importRows('sales_orders','bad',[{id:'1',nested:{x:2}}]),/scalar/);
 assert.throws(()=>data.importRows('sales_orders','bad',[{constructor:'1'}]),/Invalid column/);
 assert.throws(()=>data.importText('sales_orders','bad.html','hello',()=>[]),/csv or .json/);
 assert.throws(()=>data.parseJSON('{"ok":true}'),/record array/);
});
test('catalog/source screens escape malicious filenames or contents',()=>{
 const st={};const x=data.render('catalog',st);assert.ok(x.includes('Capability register'));
 st.enterprise.sources.push(data.importRows('sales_orders','<img src=x onerror=alert(1)>.csv',[{id:'<script>alert(1)</script>'}]));
 const a=data.render('sources',st),b=data.render('ledger',st);
 assert.ok(a.includes('&lt;img src=x'));assert.ok(!a.includes('<img src=x'));
 assert.ok(b.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
});
test('source quality audit separates orphan reference from missing target family',()=>{
 const orders=data.importRows('sales_orders','orders.csv',[{sales_order_id:'SO-1'}]);
 const jobs=data.importRows('job_cards','jobs.csv',[{job_card_id:'JC-1',sales_order_id:'SO-1'},{job_card_id:'JC-2',sales_order_id:'NOT-FOUND',purchase_order_id:'PO-NO-SOURCE'}]);
 let quality=data.assessSourceQuality([orders,jobs]);
 assert.equal(quality[1].exactLinks,1);
 assert.equal(quality[1].orphans,1);
 assert.equal(quality[1].targetsNotImported,1);
 assert.equal(quality[0].exactLinks,0);
});
