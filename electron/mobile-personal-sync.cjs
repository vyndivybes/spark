'use strict';
// Personal-only, explicit USB backup/merge. Not SPARK's AI conversation memory
// and never a business-system or autonomous tool mutation.
const fs=require('node:fs/promises');
const path=require('node:path');
const crypto=require('node:crypto');
const EMPTY=()=>({notes:[],tasks:[]});
const FILE='mobile-personal-v1.json';

function textValid(value){
 if(typeof value!=='string'||value.trim().length<1||value.length>240)return false;
 return ![...value].some(ch=>{const n=ch.codePointAt(0);return n<32||n===127;});
}
function validateRecords(data){
 if(!data||typeof data!=='object'||Array.isArray(data)||
     Object.keys(data).sort().join(',')!=='notes,tasks'||
     !Array.isArray(data.notes)||!Array.isArray(data.tasks)||
     data.notes.length>100||data.tasks.length>100)
  throw Error('Invalid personal sync snapshot.');
 if(data.notes.some(x=>!textValid(x)))throw Error('Invalid personal note.');
 if(data.tasks.some(item=>!item||typeof item!=='object'||Array.isArray(item)||
      Object.keys(item).sort().join(',')!=='done,title'||
      !textValid(item.title)||typeof item.done!=='boolean'))
  throw Error('Invalid personal task.');
 return {notes:data.notes.map(x=>x.trim()),tasks:data.tasks.map(
    item=>({title:item.title.trim(),done:item.done}))};
}
function mergeRecords(current,incoming){
 const a=validateRecords(current),b=validateRecords(incoming);
 const notes=[...new Set([...a.notes,...b.notes])];
 const tasks=[];
 const byTitle=new Map();
 for(const item of [...a.tasks,...b.tasks]){
  const index=byTitle.get(item.title);
  if(index===undefined){byTitle.set(item.title,tasks.length);tasks.push({...item});}
  else if(item.done)tasks[index].done=true;
 }
 if(notes.length>100||tasks.length>100)throw Error('Personal sync capacity exceeded (100 max per collection).');
 return {notes,tasks};
}

function createMobilePersonalStore(directory){
 if(typeof directory!=='string'||!path.isAbsolute(directory))
  throw Error('Personal sync storage requires an app-owned absolute directory.');
 const file=path.join(directory,FILE);
 let chain=Promise.resolve();
 async function read(){
  await fs.mkdir(directory,{recursive:true,mode:0o700});
  const folder=await fs.lstat(directory);
  if(folder.isSymbolicLink()||!folder.isDirectory())throw Error('Personal sync path is unsafe.');
  let info;
  try{info=await fs.lstat(file);}catch(error){
   if(error.code==='ENOENT')return EMPTY();throw error;
  }
  if(!info.isFile()||info.isSymbolicLink()||info.size>64000)
   throw Error('Personal sync file is unsafe.');
  const data=await fs.readFile(file,'utf8');
  return validateRecords(JSON.parse(data));
 }
 async function save(records){
  const validated=validateRecords(records);
  await fs.mkdir(directory,{recursive:true,mode:0o700});
  const name=path.join(directory,'.mobile-sync-'+crypto.randomBytes(8).toString('hex')+'.tmp');
  const content=JSON.stringify(validated);
  const handle=await fs.open(name,'wx',0o600);
  try{
   await handle.writeFile(content,'utf8');
   await handle.sync();
  }finally{await handle.close();}
  try{await fs.rename(name,file);}
  catch(error){await fs.rm(name,{force:true});throw error;}
  return validated;
 }
 function merge(phoneRecords){
  const job=chain.then(async()=>save(mergeRecords(await read(),phoneRecords)));
  chain=job.catch(()=>{});
  return job;
 }
 return {read,merge};
}
module.exports={createMobilePersonalStore,mergeRecords,validateRecords};
