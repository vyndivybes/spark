const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const {createMobilePersonalStore,mergeRecords,validateRecords}=require('../electron/mobile-personal-sync.cjs');
const sample={notes:['Review fork clearance'],tasks:[{title:'Inspect frame',done:false}]};

test('union-only personal sync retains both phone and PC notes and completed task flags',()=>{
 const updated=mergeRecords(
  {notes:['Review fork clearance','Wash bike'],tasks:[{title:'Inspect frame',done:false}]},
  {notes:['Wash bike','Ride 100km'],tasks:[{title:'Inspect frame',done:true},{title:'Charge lights',done:false}]});
 assert.deepEqual(updated.notes,['Review fork clearance','Wash bike','Ride 100km']);
 assert.deepEqual(updated.tasks,[{title:'Inspect frame',done:true},{title:'Charge lights',done:false}]);
 assert.deepEqual(sample,{notes:['Review fork clearance'],tasks:[{title:'Inspect frame',done:false}]});
});

test('rejects malformed snapshots, unexpected keys and hidden execution fields',()=>{
 const invalid=[
  null,{},[],{notes:[],tasks:[],execute:'shell'},
  {notes:['valid'],tasks:[{title:'x',done:'false'}]},
  {notes:[''],tasks:[]},
  {notes:['hello\u0000'],tasks:[]},
  {notes:['x'.repeat(241)],tasks:[]},
  {notes:Array(101).fill('a'),tasks:[]},
  {notes:[],tasks:[{title:'x',done:false,id:'danger'}]},
  {notes:[],tasks:[{title:'x',done:false,execute:true}]},
  {notes:[],tasks:[{title:'x'.repeat(241),done:false}]},
  {notes:[],tasks:Array(101).fill({title:'a',done:true})}
 ];
 for(const v of invalid)assert.throws(()=>validateRecords(v),{name:'Error'});
});

test('capacity exhaustion rejects the entire merge rather than dropping phone data',()=>{
 const pc={notes:Array.from({length:100},(_,i)=>'pc'+i),tasks:[]};
 assert.throws(()=>mergeRecords(pc,{notes:['extra'],tasks:[]}),/capacity/i);
});

test('explicit personal sync saves atomically under application-private directory and survives restart',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'spark-mobile-sync-'));
 try{
  const store=createMobilePersonalStore(root);
  assert.deepEqual(await store.read(),{notes:[],tasks:[]});
  const a=await store.merge(sample);
  assert.deepEqual(a,sample);
  const another=createMobilePersonalStore(root);
  const b=await another.merge({notes:['Phone entry'],tasks:[{title:'Inspect frame',done:true}]});
  assert.deepEqual(b,{notes:['Review fork clearance','Phone entry'],tasks:[{title:'Inspect frame',done:true}]});
  const listing=await fs.readdir(root);
  assert.deepEqual(listing,['mobile-personal-v1.json']);
 } finally{await fs.rm(root,{recursive:true,force:true});}
});

test('parallel sync operations are serialized without lost updates',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'spark-sync-race-'));
 try{
  const store=createMobilePersonalStore(root);
  await Promise.all([
   store.merge({notes:['alpha'],tasks:[]}),
   store.merge({notes:['beta'],tasks:[]}),
   store.merge({notes:[],tasks:[{title:'ride',done:false}]})
  ]);
  const result=await store.read();
  assert.deepEqual(new Set(result.notes),new Set(['alpha','beta']));
  assert.equal(result.tasks.length,1);
 } finally{await fs.rm(root,{recursive:true,force:true});}
});
