import React, {useEffect, useRef, useState} from 'react';
import * as THREE from 'three';

// One shared, genuinely three-dimensional core for the dashboard and cockpit.
export default function Visualizer({isListening, intensity=0, width=600, height=400, active=true}) {
    const mount=useRef(null);
    const signal=useRef({isListening,intensity});
    const [fallback,setFallback]=useState(false);
    useEffect(()=>{signal.current={isListening,intensity};},[isListening,intensity]);
    useEffect(()=>{
        if(!active)return undefined;
        const element=mount.current;
        let renderer;
        try {renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});}
        catch {setFallback(true);return undefined;}
        renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.5));
        element.appendChild(renderer.domElement);
        const scene=new THREE.Scene();
        const camera=new THREE.PerspectiveCamera(38,1,.1,100);
        camera.position.set(0,.3,7.8);
        const core=new THREE.Group();scene.add(core);
        const shell=new THREE.Mesh(new THREE.IcosahedronGeometry(1.08,2),new THREE.MeshPhongMaterial({color:0x267d99,emissive:0x062b3c,shininess:100,transparent:true,opacity:.85,flatShading:true}));
        const lattice=new THREE.Mesh(new THREE.IcosahedronGeometry(1.12,2),new THREE.MeshBasicMaterial({color:0x87eafa,wireframe:true,transparent:true,opacity:.28}));
        core.add(shell,lattice);
        const rings=[];
        for(let i=0;i<3;i++){
            const ring=new THREE.Mesh(new THREE.TorusGeometry(1.55+i*.24,.009,6,100),new THREE.MeshBasicMaterial({color:i===1?0xb8d4ff:0x6cdff2,transparent:true,opacity:.6-i*.1}));
            ring.rotation.set(.65+i*.75,.3+i*.55,i*.6);core.add(ring);rings.push(ring);
        }
        const points=[];
        for(let i=0;i<180;i++){const a=i*2.399963,r=2.2+(i%11)*.16,y=1-(i/179)*2;points.push(Math.cos(a)*Math.sqrt(1-y*y)*r,y*r,Math.sin(a)*Math.sqrt(1-y*y)*r);}
        const dust=new THREE.Points(new THREE.BufferGeometry().setAttribute('position',new THREE.Float32BufferAttribute(points,3)),new THREE.PointsMaterial({color:0x86dce9,size:.018,transparent:true,opacity:.55}));scene.add(dust);
        scene.add(new THREE.AmbientLight(0x6faec9,1.7));
        const key=new THREE.PointLight(0x9ef3ff,14,15);key.position.set(-3,3,4);scene.add(key);
        const rim=new THREE.PointLight(0x6279ff,10,15);rim.position.set(3,-2,1);scene.add(rim);
        const resize=()=>{const box=element.getBoundingClientRect();renderer.setSize(Math.max(1,box.width),Math.max(1,box.height));camera.aspect=Math.max(1,box.width)/Math.max(1,box.height);camera.updateProjectionMatrix();};
        const observer=new ResizeObserver(resize);observer.observe(element);resize();
        const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
        let frame,last=0,elapsed=0;
        const pointer={x:0,y:0};
        const move=event=>{const box=element.getBoundingClientRect();pointer.x=(event.clientX-box.left)/box.width-.5;pointer.y=(event.clientY-box.top)/box.height-.5;};
        const reset=()=>{pointer.x=pointer.y=0;};
        element.addEventListener('pointermove',move);element.addEventListener('pointerleave',reset);
        const draw=time=>{
            frame=requestAnimationFrame(draw);
            if(document.hidden||time-last<33)return;
            const delta=Math.min((time-last)/1000,.05);last=time;
            if(!reduced.matches){elapsed+=delta;core.rotation.y=elapsed*.12+pointer.x*.2;core.rotation.x=pointer.y*.12;dust.rotation.y=-elapsed*.025;rings[0].rotation.z=elapsed*.12;rings[2].rotation.x=elapsed*.09;}
            const amplitude=Math.max(0,Math.min(1,Number(signal.current.intensity)||0));
            shell.scale.setScalar(1+amplitude*.16);lattice.scale.setScalar(1+amplitude*.18);
            shell.material.emissiveIntensity=signal.current.isListening?1.8:1;
            renderer.render(scene,camera);
        };draw(0);
        return ()=>{cancelAnimationFrame(frame);observer.disconnect();element.removeEventListener('pointermove',move);element.removeEventListener('pointerleave',reset);scene.traverse(object=>{object.geometry?.dispose();if(object.material)object.material.dispose();});renderer.dispose();renderer.domElement.remove();};
    },[active]);
    return <div className="spatial-core" style={{width,height}}><div ref={mount} className="spatial-core-scene" aria-hidden="true"/>{fallback&&<div className="spatial-core-fallback" aria-hidden="true"/>}<span className="spatial-core-caption">{isListening?'Voice channel open':'Voice standby'}</span></div>;
}
