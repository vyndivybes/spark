const path = require('node:path');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const run = promisify(execFile);

async function readLocalRecords(root, {dataRoot, python=process.env.SPARK_PYTHON||'python', vayuDataRoot}={}) {
    if(!dataRoot) throw Error('Local workspace storage is unavailable.');
    const args=[path.join(root,'backend','spark_local_records.py'),'--data-root',dataRoot];
    if(vayuDataRoot) args.push('--vayu-data-root',vayuDataRoot);
    const {stdout}=await run(python,args,{windowsHide:true,timeout:15000,maxBuffer:2_000_000,env:{...process.env,PYTHONIOENCODING:'utf-8'}});
    const data=JSON.parse(stdout);
    if(!Array.isArray(data.records)||!Array.isArray(data.spaces))throw Error('Invalid local records.');
    return data;
}
function recordsGraph(data) {
    const nodes=[],edges=[];
    for(const space of data.spaces) {
        const records=data.records.filter(r=>r.space===space.id);
        if(!records.length)continue;
        const parent='space:'+space.id;
        nodes.push({id:parent,label:space.label,type:'project'});
        for(const record of records.slice(0,200)) {
            nodes.push({id:record.id,label:record.title,type:record.kind});
            edges.push({source:parent,target:record.id});
        }
    }
    return {nodes,edges,source:data.source,modifiedAt:data.readAt,totalNodes:nodes.length,totalEdges:edges.length};
}
async function readBrainDisplay(root,options) {return recordsGraph(await readLocalRecords(root,options));}
module.exports={readBrainDisplay,readLocalRecords,recordsGraph};
