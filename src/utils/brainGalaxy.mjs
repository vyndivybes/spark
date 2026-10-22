export const SPECTRUM_COLORS=['#ffb454','#55efb1','#57dbff','#c48aff'];
export const NODE_COLORS={organization:'#8f9cff',division:'#57dbff',project:'#55efb1',contact:'#ffca80',document:'#c48aff',decision:'#ff83b5',record:'#a4c9de'};

export function voiceBands(spectrum) {
    const bins=spectrum?.bins;
    if (!bins?.length || !(spectrum.sampleRate>0) || !(spectrum.fftSize>0)) return [0,0,0,0];
    return [[80,300],[300,1500],[1500,5000],[5000,10000]].map(([lo,hi])=>{
        const start=Math.max(1,Math.ceil(lo*spectrum.fftSize/spectrum.sampleRate));
        const end=Math.min(bins.length-1,Math.floor(hi*spectrum.fftSize/spectrum.sampleRate));
        if(end<start)return 0;
        let sum=0;for(let i=start;i<=end;i++)sum+=bins[i]*bins[i];
        return Math.max(0,Math.min(1,(Math.sqrt(sum/(end-start+1))/255-.035)/.965));
    });
}

function hash(value){let h=2166136261;for(const c of String(value))h=Math.imul(h^c.charCodeAt(0),16777619);return (h>>>0)/4294967295;}

export function layoutBrain(graph) {
    if(!graph?.nodes?.length)return {nodes:[],edges:[],groups:[]};
    const groups=[...new Set(graph.nodes.map(n=>n.type))].sort();
    const members=new Map(groups.map(g=>[g,graph.nodes.filter(n=>n.type===g)]));
    const nodes=graph.nodes.map(n=>{
        const group=groups.indexOf(n.type), list=members.get(n.type), i=list.indexOf(n);
        const az=group/groups.length*Math.PI*2;
        const theta=i*2.3999632297;
        const y=1-2*(i+.5)/list.length;
        const r=Math.sqrt(1-y*y);
        const spread=.16+.31*Math.cbrt(hash(n.id));
        return {...n,group,x:Math.cos(az)*.92+Math.cos(theta)*r*spread,
            y:Math.sin(az)*.59+y*spread,z:Math.sin(theta)*r*spread+Math.sin(az*2)*.19,
            size:1.2+hash(n.id+'size')*1.7,degree:0};
    });
    const index=new Map(nodes.map((n,i)=>[n.id,i]));
    const edges=(graph.edges||[]).filter(e=>index.has(e.source)&&index.has(e.target)).map(e=>({s:index.get(e.source),t:index.get(e.target)}));
    const neighbors=nodes.map(()=>[]);
    for(const e of edges){nodes[e.s].degree++;nodes[e.t].degree++;neighbors[e.s].push(e.t);neighbors[e.t].push(e.s);}
    // Graph distance gives traveling pulses a causal path through real links.
    const distance=nodes.map(()=>Infinity);
    for(let root=0;root<nodes.length;root++){
        if(Number.isFinite(distance[root]))continue;
        let queue=[root];distance[root]=0;
        for(let q=0;q<queue.length;q++)for(const next of neighbors[queue[q]]){
            if(!Number.isFinite(distance[next])){distance[next]=distance[queue[q]]+1;queue.push(next);}
        }
    }
    return {nodes,groups,edges:edges.map(e=>({
        s:distance[e.s]<=distance[e.t]?e.s:e.t,
        t:distance[e.s]<=distance[e.t]?e.t:e.s,
        hop:Math.min(distance[e.s],distance[e.t])
    }))};
}
