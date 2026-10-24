const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {validateBlueprint,verifyBlueprintHtml}=require('../electron/rea-blueprint.cjs');
const blueprint={title:'Original stock app',description:'Local stock records.',entities:[{key:'stock',label:'Stock',fields:[{key:'name',label:'Name',type:'text',required:true,options:[]},{key:'quantity',label:'Quantity',type:'number',required:false,options:[]}]}],limitations:['Local records only.']};
const template=fs.readFileSync(path.join(__dirname,'../backend/spark_rea_app.html'),'utf8').replace(/^\uFEFF/,'');
test('dynamic apps contain only validated data inside the exact shipped renderer',()=>{
 const source=template.replace('%%SPARK_BLUEPRINT%%',JSON.stringify(blueprint));
 assert.deepEqual(verifyBlueprintHtml(source,template),blueprint);
 assert.throws(()=>verifyBlueprintHtml(source+'<script>bad()</script>',template),/renderer/);
 assert.throws(()=>verifyBlueprintHtml(source.replace('No network','Network enabled'),template),/renderer/);
});
test('model output cannot inject scripts, dependencies or prototype keys',()=>{
 for(const malicious of [{...blueprint,script:'bad()'},{...blueprint,title:'</script><script>bad()</script>'},{...blueprint,description:'https://evil.test/'}])assert.throws(()=>validateBlueprint(malicious));
 for(const key of ['constructor','__proto__','id']){
  const b=JSON.parse(JSON.stringify(blueprint));b.entities[0].fields[0].key=key;assert.throws(()=>validateBlueprint(b));
 }
});
test('invalid field contracts and duplicate names fail before any browser is created',()=>{
 const duplicate=JSON.parse(JSON.stringify(blueprint));duplicate.entities.push(duplicate.entities[0]);assert.throws(()=>validateBlueprint(duplicate));
 const field=JSON.parse(JSON.stringify(blueprint));field.entities[0].fields[0].type='javascript';assert.throws(()=>validateBlueprint(field));
});

test('Python-normalized LF artifacts verify against Windows CRLF recipe files',()=>{
 const lf=template.replace(/\r\n/g,'\n');
 assert.deepEqual(verifyBlueprintHtml(lf.replace('%%SPARK_BLUEPRINT%%',JSON.stringify(blueprint)),lf.replace(/\n/g,'\r\n')),blueprint);
});
