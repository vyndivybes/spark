const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs/promises');
const os=require('node:os');
const {readBrainDisplay}=require('../electron/brain-display.cjs');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const localPython=path.join(root,'.venv',process.platform==='win32'?'Scripts':'bin',process.platform==='win32'?'python.exe':'python');
const python=process.env.SPARK_PYTHON || (require('node:fs').existsSync(localPython)?localPython:'python');

test('Atlas display reads real local document metadata without exposing note bodies',async()=>{
    const dataRoot=await fs.mkdtemp(path.join(os.tmpdir(),'spark-records-'));
    try {
        execFileSync(python,['-c',
            "import sys,sqlite3;from pathlib import Path;p=Path(sys.argv[1])/'knowledge'/'personal'/'knowledge.sqlite3';p.parent.mkdir(parents=True);c=sqlite3.connect(p);c.execute('CREATE TABLE documents(id TEXT,name TEXT,uploaded REAL,body TEXT)');c.execute('INSERT INTO documents VALUES(?,?,?,?)',('doc-1','Personal project note',1,'PRIVATE_NOTE_BODY'));c.commit();c.close()",dataRoot],{windowsHide:true});
        const graph=await readBrainDisplay(root,{dataRoot,python});
        assert.equal(graph.source,'Existing local SPARK records');
        assert.equal(graph.nodes.length,2);
        assert.equal(graph.edges.length,1);
        assert.ok(graph.nodes.some(n=>n.label==='Personal project note'));
        assert.ok(!JSON.stringify(graph).includes('PRIVATE_NOTE_BODY'));
        for(const n of graph.nodes) assert.deepEqual(Object.keys(n).sort(),['id','label','type']);
        const ids=new Set(graph.nodes.map(n=>n.id));
        for(const e of graph.edges){assert.ok(ids.has(e.source));assert.ok(ids.has(e.target));}
    } finally {await fs.rm(dataRoot,{recursive:true,force:true});}
});

test('graph loader ignores bundled sample HTML and embedded scripts',async()=>{
    const dir=await fs.mkdtemp(path.join(os.tmpdir(),'spark-graph-'));
    const target=path.join(dir,'vendor/vayu-workspace');
    await fs.mkdir(target,{recursive:true});
    try{
        await fs.writeFile(path.join(target,'VAYU-Knowledge-Sphere-Live.html'),
            '<script id="initial-data" type="application/json">{ "nodes": [] };process.exit(1)</script>');
        const graph=await readBrainDisplay(root,{dataRoot:dir,python});
        assert.deepEqual(graph.nodes,[]);
        assert.deepEqual(graph.edges,[]);
    }finally{await fs.rm(dir,{recursive:true,force:true});}
});

test('frequency colours follow measured FFT frequency ranges and silence stays zero',async()=>{
    const {voiceBands}=await import('../src/utils/brainGalaxy.mjs');
    for(const [frequency,expected] of [[187.5,0],[937.5,1],[3000,2],[7500,3]]){
        const bins=new Uint8Array(256);bins[Math.round(frequency/93.75)]=255;
        const result=voiceBands({bins,sampleRate:48000,fftSize:512});
        assert.ok(result[expected]>.06);
        result.forEach((value,i)=>{if(i!==expected)assert.equal(value,0);});
    }
    assert.deepEqual(voiceBands(null),[0,0,0,0]);
    assert.deepEqual(voiceBands({bins:new Uint8Array(256),sampleRate:48000,fftSize:512}),[0,0,0,0]);
});

test('galaxy layout preserves graph topology and separates modules around the center',async()=>{
    const {layoutBrain}=await import('../src/utils/brainGalaxy.mjs');
    const graph={nodes:[{id:'a',type:'project'},{id:'b',type:'project'},{id:'c',type:'document'}],
        edges:[{source:'a',target:'b'},{source:'b',target:'c'}]};
    const model=layoutBrain(graph);
    assert.equal(model.nodes.length,3);assert.equal(model.edges.length,2);
    for(const e of model.edges){
        const ids=[model.nodes[e.s].id,model.nodes[e.t].id];
        assert.ok(graph.edges.some(link=>ids.includes(link.source)&&ids.includes(link.target)));
        assert.ok(Number.isFinite(e.hop));
    }
    assert.deepEqual(layoutBrain(null),{nodes:[],edges:[],groups:[]});
});
