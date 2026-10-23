import React, {useEffect, useMemo, useRef, useState} from 'react';
import {layoutBrain, voiceBands, NODE_COLORS, SPECTRUM_COLORS} from '../utils/brainGalaxy.mjs';

export default function Visualizer({graph, graphError='', getSpectrum, isListening=false, width=600, height=400, active=true}) {
    const mount=useRef(null), host=useRef(null), caption=useRef(null);
    const signal=useRef({getSpectrum,isListening});
    const [unavailable,setUnavailable]=useState(false);
    const [hover,setHover]=useState(null);
    const model=useMemo(()=>layoutBrain(graph),[graph]);
    useEffect(()=>{signal.current={getSpectrum,isListening};},[getSpectrum,isListening]);
    useEffect(()=>{
        if(!active)return undefined;
        const canvas=mount.current, element=host.current;
        const ctx=canvas.getContext('2d',{alpha:true});
        if(!ctx){setUnavailable(true);return undefined;}
        const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
        const points=model.nodes.map(()=>({x:0,y:0,z:0,size:0}));
        const stars=Array.from({length:360},(_,i)=>({
            angle:i*2.39996323, radius:.18+Math.sqrt((i+.5)/360)*1.9,
            z:Math.sin(i*9.41)*.8, size:.35+(i%5)*.22
        }));
        const pointer={x:0,y:0,tx:0,ty:0}, bands=[0,0,0,0], previous=[0,0,0,0], pulses=[];
        let w=1,h=1,frame=0,last=0,elapsed=0,lastPulse=-1,selected=-1;
        const resize=()=>{
            const b=canvas.getBoundingClientRect();w=Math.max(1,b.width);h=Math.max(1,b.height);
            const dpr=Math.min(window.devicePixelRatio||1,1.5);
            canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
        };
        const observer=new ResizeObserver(resize);observer.observe(canvas);resize();
        const move=e=>{
            const b=canvas.getBoundingClientRect();
            pointer.tx=(e.clientX-b.left)/b.width-.5;pointer.ty=(e.clientY-b.top)/b.height-.5;
            const x=e.clientX-b.left,y=e.clientY-b.top;
            const hit=points.findIndex(p=>Math.hypot(p.x-x,p.y-y)<12);
            if(hit!==selected){selected=hit;setHover(hit<0?null:model.nodes[hit]);}
        };
        const leave=()=>{pointer.tx=pointer.ty=0;selected=-1;setHover(null);};
        canvas.addEventListener('pointermove',move);canvas.addEventListener('pointerleave',leave);
        const draw=now=>{
            frame=requestAnimationFrame(draw);
            if(document.hidden||now-last<33)return;
            const dt=Math.min((now-last)/1000,.05);last=now;
            if(!reduced.matches)elapsed+=dt;
            const t=elapsed;
            const measured=voiceBands(signal.current.isListening?signal.current.getSpectrum?.():null);
            for(let i=0;i<4;i++)bands[i]+=(measured[i]-bands[i])*.24;
            const energy=Math.max(...bands);
            if(!reduced.matches && signal.current.isListening && energy>.07 && t-lastPulse>.14){
                for(let i=0;i<4;i++)if(bands[i]>.06 && (bands[i]>previous[i]+.018||t-lastPulse>.38)){
                    pulses.push({at:t,band:i,power:bands[i]});
                }
                if(pulses.some(p=>p.at===t))lastPulse=t;
            }
            for(let i=0;i<4;i++)previous[i]=bands[i];
            while(pulses.length && (t-pulses[0].at>5||pulses.length>24))pulses.shift();
            pointer.x+=(pointer.tx-pointer.x)*.055;pointer.y+=(pointer.ty-pointer.y)*.055;
            const px=reduced.matches?0:pointer.x,py=reduced.matches?0:pointer.y;
            element.style.setProperty('--galaxy-look-x',`${-py*13}deg`);
            element.style.setProperty('--galaxy-look-y',`${px*17}deg`);
            element.style.setProperty('--galaxy-voice',String(1+energy*.055));
            const scale=Math.min(w*.35,h*.35), cx=w*.5,cy=h*.47;
            const yaw=t*.055+px*.22,tilt=Math.sin(t*.07)*.14+py*.2;
            const project=(x,y,z)=>{
                const a=x*Math.cos(yaw)-z*Math.sin(yaw),b=x*Math.sin(yaw)+z*Math.cos(yaw);
                const yy=y*Math.cos(tilt)-b*Math.sin(tilt),zz=y*Math.sin(tilt)+b*Math.cos(tilt);
                const perspective=3.8/(3.8-zz);
                return {x:cx+a*scale*perspective+px*13,y:cy+yy*scale*perspective+py*9,z:zz};
            };
            ctx.clearRect(0,0,w,h);
            ctx.globalCompositeOperation='lighter';
            // Decorative star field. Knowledge nodes and links below come only
            // from the supplied Atlas graph, never from generated connections.
            for(let i=0;i<stars.length;i++){
                const s=stars[i],a=s.angle+t*.012*(i%2?1:-1);
                const p=project(Math.cos(a)*s.radius,Math.sin(a)*s.radius*.68,s.z);
                ctx.fillStyle=`rgba(${i%4===0?'180,150,255':'150,208,244'},${.12+(i%11)/35})`;
                ctx.beginPath();ctx.arc(p.x,p.y,s.size,0,Math.PI*2);ctx.fill();
            }
            // Inclined orbital trails revolve in depth around the wordmark.
            for(let orbit=0;orbit<3;orbit++){
                ctx.strokeStyle=['#748aff18','#49d9ff20','#cf7eff15'][orbit];ctx.lineWidth=.8;ctx.beginPath();
                for(let k=0;k<=100;k++){
                    const a=k/100*Math.PI*2+t*(.025+orbit*.006),r=.72+orbit*.23;
                    const p=project(Math.cos(a)*r,Math.sin(a)*r*(.3+orbit*.14),Math.sin(a+orbit)*.5);
                    if(k===0)ctx.moveTo(p.x,p.y);else ctx.lineTo(p.x,p.y);
                }ctx.stroke();
                const a=t*(.11+orbit*.045)+orbit*2;
                const p=project(Math.cos(a)*(1+orbit*.14),Math.sin(a)*(.35+orbit*.14),Math.sin(a+orbit)*.5);
                ctx.fillStyle=['#86a6ff','#8ff6e5','#f6b2ff'][orbit];ctx.beginPath();ctx.arc(p.x,p.y,2.1,0,Math.PI*2);ctx.fill();
            }
            model.nodes.forEach((n,i)=>{
                const a=n.group/Math.max(1,model.groups.length)*Math.PI*2;
                const gx=Math.cos(a)*.92,gy=Math.sin(a)*.59;
                const expansion=1+bands[n.group%4]*.42;
                const self=t*(.06+n.group*.006),dx=(n.x-gx)*expansion,dz=n.z*expansion;
                const p=project(gx+dx*Math.cos(self)-dz*Math.sin(self),gy+(n.y-gy)*expansion,dx*Math.sin(self)+dz*Math.cos(self));
                points[i]={...p,size:n.size*(1+(p.z+1)*.18)+Math.min(n.degree,12)*.11};
            });
            for(const e of model.edges){
                const a=points[e.s],b=points[e.t];
                const highlighted=selected===e.s||selected===e.t;
                ctx.strokeStyle=highlighted?'#b8f2ffb0':'#70a6da32';ctx.lineWidth=highlighted?1.3:.65;
                ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();
                // A voice-triggered wave advances hop by hop along real edges.
                for(const pulse of pulses){
                    const progress=(t-pulse.at)*1.65-e.hop*.22;
                    if(progress<0||progress>1)continue;
                    const start=a, end=b;
                    const x=start.x+(end.x-start.x)*progress,y=start.y+(end.y-start.y)*progress;
                    ctx.strokeStyle=SPECTRUM_COLORS[pulse.band];ctx.globalAlpha=.3+pulse.power*.5;
                    ctx.lineWidth=1.2+pulse.power;ctx.beginPath();
                    ctx.moveTo(start.x+(end.x-start.x)*Math.max(0,progress-.18),start.y+(end.y-start.y)*Math.max(0,progress-.18));ctx.lineTo(x,y);ctx.stroke();
                    ctx.fillStyle=SPECTRUM_COLORS[pulse.band];ctx.beginPath();ctx.arc(x,y,2+pulse.power*2,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;
                }
            }
            points.forEach((p,i)=>{
                const n=model.nodes[i],color=NODE_COLORS[n.type]||'#a4c9de';
                const boost=bands[n.group%4];
                ctx.globalAlpha=.55+Math.min(.45,(p.z+1)*.14+boost*.5);ctx.fillStyle=color;
                ctx.beginPath();ctx.arc(p.x,p.y,p.size+boost*3,0,Math.PI*2);ctx.fill();
                ctx.globalAlpha=.09+boost*.13;ctx.beginPath();ctx.arc(p.x,p.y,p.size*3+boost*7,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;
            });
            const occupied=[{x:cx-175,y:cy-65,w:350,h:140}];
            const labels=model.nodes.map((n,i)=>({n,i})).filter(({n,i})=>n.degree>8||i===selected)
                .sort((a,b)=>b.n.degree-a.n.degree).slice(0,18);
            ctx.font='10px Segoe UI';ctx.fillStyle='#b6cfdfb0';
            for(const {n,i} of labels){
                const p=points[i],text=n.label.slice(0,27);
                const box={x:p.x+p.size+6,y:p.y-8,w:ctx.measureText(text).width+7,h:17};
                if(box.x<15||box.x+box.w>w-15||box.y<20||occupied.some(b=>box.x<b.x+b.w&&box.x+box.w>b.x&&box.y<b.y+b.h&&box.y+box.h>b.y))continue;
                occupied.push(box);ctx.fillText(text,box.x,box.y+11);
            }
            // Frequency bars are actual measured band energies, silent at rest.
            for(let i=0;i<4;i++){
                ctx.fillStyle=SPECTRUM_COLORS[i];ctx.globalAlpha=.4+bands[i]*.6;
                for(let k=0;k<7;k++){
                    const bar=Math.max(1,bands[i]*(11-Math.abs(k-3)*1.7));
                    ctx.fillRect(cx-49+i*28+k*3,cy+Math.min(w,h)*.12-bar,1.5,bar);
                }
            }
            ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';
            if(caption.current)caption.current.textContent=unavailable?'Visualization unavailable':signal.current.isListening?(energy>.025?'VOICE FREQUENCIES · LIVE':'MIC ENABLED · AWAITING VOICE'):'MIC MUTED · GALAXY DRIFT';
        };
        frame=requestAnimationFrame(draw);
        return ()=>{cancelAnimationFrame(frame);observer.disconnect();canvas.removeEventListener('pointermove',move);canvas.removeEventListener('pointerleave',leave);};
    },[active,model]);
    return <div ref={host} className="spatial-core brain-galaxy" style={{width,height}}>
        <div className="galaxy-nebula" aria-hidden="true"/>
        <canvas ref={mount} className="spatial-core-scene" aria-hidden="true"/>
        <div className="galaxy-wordmark" aria-label="SPARK"><div className="galaxy-wordmark-depth" aria-hidden="true">{[0,1,2,3,4,5].map(i=><span key={i} style={{transform:`translateZ(${-i*2}px)`}}>SPARK</span>)}</div><strong>SPARK</strong><small>NEURAL UNIVERSE</small></div>
        {hover&&<div className="galaxy-node-detail"><strong>{hover.label}</strong><span>{hover.type} · {hover.degree} connections</span></div>}
        <div className="galaxy-provenance">{graph?.nodes?.length?`${graph.source} · ${graph.nodes.length} nodes · ${graph.edges.length} links`:graphError||'No brain graph loaded'}</div>
        <span ref={caption} className="spatial-core-caption">{unavailable?'Visualization unavailable':'MIC MUTED · GALAXY DRIFT'}</span>
        <div className="galaxy-frequency-key" aria-label="Voice frequency colours">{['80–300 Hz','300–1500 Hz','1.5–5 kHz','5–10 kHz'].map((label,i)=><span key={label} style={{color:SPECTRUM_COLORS[i]}}>{label}</span>)}</div>
    </div>;
}
