'use strict';
function validateBlueprint(b){
 const object=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')===[...keys].sort().join(',');
 const text=(v,max)=>typeof v==='string'&&v.trim().length>0&&v.length<=max&&!/[\x00-\x08\x0b\x0c\x0e-\x1f]|<\s*\/?\s*[a-z!]|https?:\/\/|javascript:|data:/i.test(v);
 const key=v=>typeof v==='string'&&/^[a-z][a-z0-9_]{0,31}$/.test(v)&&!['id','__proto__','constructor','prototype'].includes(v);
 if(!object(b,['title','description','entities','limitations'])||!text(b.title,80)||!text(b.description,600)||JSON.stringify(b).length>24000||!Array.isArray(b.limitations)||b.limitations.length<1||b.limitations.length>8||!b.limitations.every(v=>text(v,240))||!Array.isArray(b.entities)||b.entities.length<1||b.entities.length>6)throw Error('Invalid app blueprint.');
 const entities=new Set();
 for(const e of b.entities){
  if(!object(e,['key','label','fields'])||!key(e.key)||entities.has(e.key)||!text(e.label,60)||!Array.isArray(e.fields)||e.fields.length<1||e.fields.length>10)throw Error('Invalid blueprint entity.');
  entities.add(e.key);const fields=new Set();
  for(const f of e.fields){
   if(!object(f,['key','label','type','required','options'])||!key(f.key)||fields.has(f.key)||!text(f.label,60)||!['text','number','date','boolean','select'].includes(f.type)||typeof f.required!=='boolean'||!Array.isArray(f.options)||!f.options.every(v=>text(v,60))||new Set(f.options).size!==f.options.length||(f.type==='select'?(f.options.length<2||f.options.length>12):f.options.length!==0))throw Error('Invalid blueprint field.');
   fields.add(f.key);
  }
  if(e.fields[0].type!=='text')throw Error('First field must be text.');
 }
 return b;
}
function verifyBlueprintHtml(source,template){
 source=source.replace(/^\uFEFF/,'').replace(/\r\n/g,'\n');
 const marker='%%SPARK_BLUEPRINT%%',parts=template.replace(/^\uFEFF/,'').replace(/\r\n/g,'\n').split(marker);
 if(parts.length!==2||!source.startsWith(parts[0])||!source.endsWith(parts[1]))throw Error('Generated app differs from the shipped renderer.');
 const middle=source.slice(parts[0].length,source.length-parts[1].length);
 return validateBlueprint(JSON.parse(middle));
}
const BLUEPRINT_TEST=`(()=>{
 const $=id=>document.getElementById(id),config=JSON.parse($('blueprint').textContent),entity=config.entities[0],checks=[];
 function check(name,ok){if(!ok)throw Error(name);checks.push(name);}
 check('blueprint title',$('app-title').textContent===config.title);
 for(const f of entity.fields){const el=$('f-'+f.key);if(f.type==='boolean')el.checked=true;else el.value=f.type==='number'?'7':f.type==='date'?'2026-10-24':f.type==='select'?f.options[0]:'Smoke record';}
 $('record-form').requestSubmit();check('create record',$('rows').children.length===1);
 $('rows').querySelector('[data-edit]').click();$('f-'+entity.fields[0].key).value='Smoke edited';$('record-form').requestSubmit();
 check('edit record',$('rows').textContent.includes('Smoke edited'));
 $('search').value='no-match-xyz';$('search').dispatchEvent(new Event('input'));check('search filters',$('rows').children.length===0);
 $('search').value='';$('search').dispatchEvent(new Event('input'));check('search restores',$('rows').children.length===1);
 if(entity.fields.some(f=>f.type==='number'))check('numeric totals',$('totals').textContent.includes('7'));
 check('local persistence',localStorage.getItem('spark-blueprint-records-v1').includes('Smoke edited'));
 return checks;
})()`;
const BLUEPRINT_RELOAD_TEST=`(()=>{if(!document.getElementById('rows').textContent.includes('Smoke edited'))throw Error('reload persistence');window.confirm=()=>true;document.querySelector('[data-delete]').click();if(document.getElementById('rows').children.length)throw Error('delete record');return ['reload persistence','delete record'];})()`;
module.exports={validateBlueprint,verifyBlueprintHtml,BLUEPRINT_TEST,BLUEPRINT_RELOAD_TEST};
