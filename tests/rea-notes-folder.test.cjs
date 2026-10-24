const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
test('shipped notes folder handler reads the named input and creates one folder',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../backend/spark_rea_notes.html'),'utf8');
 const handler=source.match(/\$\('add-folder'\)\.onclick=\(\)=>\{[^\n]+/)[0];
 const elements={'add-folder':{},'folder-name':{value:' Flight '}};
 const state={folders:['Inbox']};let saves=0,renders=0;
 vm.runInNewContext(handler,{$:id=>elements[id],state,save:()=>saves++,render:()=>renders++});
 elements['add-folder'].onclick();elements['add-folder'].onclick();
 assert.deepEqual(state.folders,['Inbox','Flight']);assert.equal(saves,2);assert.equal(renders,2);
});
