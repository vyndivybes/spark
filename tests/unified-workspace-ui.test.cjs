'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const read=path=>fs.readFileSync(path,'utf8');

test('VAYU inline application scripts remain syntactically valid',()=>{
  const html=read('vendor/vayu-workspace/VAYU-Knowledge-Sphere-Live.html');
  let parsed=0;
  for(const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)){
    const [,attributes,body]=match;
    if(/type="(?:module|application\/json)"/i.test(attributes)||!body.trim())continue;
    new vm.Script(body,{filename:'VAYU-Knowledge-Sphere-Live.html'});
    parsed++;
  }
  assert.ok(parsed>=3,'Expected legacy, analytics and workspace application scripts');
});

test('VAYU departmental pages do not repeat the founder KPI dashboard',()=>{
  const html=read('vendor/vayu-workspace/VAYU-Knowledge-Sphere-Live.html');
  assert.match(html,/sectionItems=page==='today'\|\|page==='intelligence'/);
  assert.match(html,/page==='today'\?\x60<div class="wmetrics">/);
  assert.match(html,/class="wcompact"/);
  assert.match(html,/Related knowledge references \(historical\)/);
  assert.match(html,/source references, not verified live business records/);
  assert.match(html,/Saved on this PC/);
  assert.match(html,/Search business knowledge/);
  assert.match(html,/No records for this selection/);
  assert.match(html,/page==='knowledge'\?'':`<div class="wcompact"/);
});

test('Four main analytics choices preserve specialist capabilities',()=>{
  const html=read('vendor/vayu-workspace/VAYU-Knowledge-Sphere-Live.html');
  for(const view of ['Overview','Performance','Operations','Data Explorer']) assert.ok(html.includes(",'"+view+"']"));
  for(const view of ['Data quality','Records','Capability audit','Source intake','Ledger trace'])
    assert.ok(html.includes(",'"+view+"']"));
  assert.match(html,/Advanced analytics views/);
  assert.match(html,/More analysis &amp; data tools/);
});

test('SPARK navigation keeps core destinations and gates specialized controls',()=>{
  const panel=read('src/components/WorkspacePanel.jsx');
  const app=read('src/App.jsx');
  for(const label of ['Home','Workspace','Knowledge','Tools','Improve SPARK','Ask SPARK','Settings'])
    assert.ok(panel.includes('>'+label+'</button>')||panel.includes('"'+label+'"'),'Missing '+label);
  assert.match(panel,/advanced&&<>/);
  assert.match(panel,/Developer screens/);
  assert.match(panel,/Agent controls/);
  assert.ok(app.includes('onSettings={() => {setShowWorkspace(false);setShowSettings(true);}}'));
});

test('Personal and business storage boundaries remain unchanged',()=>{
  const vayu=read('vendor/vayu-workspace/VAYU-Knowledge-Sphere-Live.html');
  const start=read('vendor/vayu-workspace/start.py');
  assert.match(vayu,/data-space="business"/);
  assert.match(vayu,/data-space="personal"/);
  assert.match(vayu,/api\/workspace\?space=/);
  assert.match(start,/personal','business/);
});
