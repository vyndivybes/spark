const fs = require('node:fs/promises');
const path = require('node:path');

// The same canonical inventory used by spark_neural_atlas.py. Never execute
// graph-data.js or copy note bodies into the renderer to obtain a display graph.
async function readBrainDisplay(root) {
    const filename = path.join(root,'vendor','vayu-workspace','VAYU-Knowledge-Sphere-Live.html');
    const stat = await fs.stat(filename);
    if (stat.size > 16_000_000) throw Error('Neural Atlas inventory is too large.');
    const html = await fs.readFile(filename,'utf8');
    const match = html.match(/<script id="initial-data" type="application\/json">\s*(\{[\s\S]*?\})\s*<\/script>/);
    if (!match) throw Error('Neural Atlas inventory is unavailable.');
    const data = JSON.parse(match[1]);
    if (!Array.isArray(data.nodes) || !Array.isArray(data.edges)) throw Error('Invalid Neural Atlas graph.');
    const nodes = data.nodes.slice(0,1200).filter(n=>typeof n?.id==='string').map(n=>({
        id:n.id.slice(0,200), label:String(n.title||n.id).slice(0,100), type:String(n.type||'record').slice(0,40)
    }));
    const known = new Set(nodes.map(n=>n.id));
    const edges = data.edges.filter(e=>known.has(e?.source)&&known.has(e?.target)&&e.source!==e.target)
        .slice(0,4000).map(e=>({source:e.source,target:e.target}));
    return {nodes,edges,source:'Neural Atlas snapshot',modifiedAt:stat.mtime.toISOString(),
        totalNodes:data.nodes.length,totalEdges:data.edges.length};
}
module.exports={readBrainDisplay};
