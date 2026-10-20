import React from 'react';
import {createRoot} from 'react-dom/client';
import JarvisPanel from '../src/components/JarvisPanel';
import '../src/index.css';
let signedIn=false;
const listeners=new Set();window.__pcRequests=[];
const socket={connected:true,workspaceToken:'fixture-token',on:(event,fn)=>listeners.add(fn),off:(event,fn)=>listeners.delete(fn),emit:(event,request)=>{
    window.__pcRequests.push(request);
    const result=request.action==='pc_task_history'?[]:{id:'fixture-task',plan_hash:'reviewed-fixture-hash',goal:'Save advisory',
        steps:request.payload.steps||[{action:'write',path:'C:/fixture/advisory.md',content:'Fixture advisory report'}],
        state:request.action==='pc_task_run'?'completed':'awaiting_approval',results:request.action==='pc_task_run'?[{ok:true,path:'C:/fixture/advisory.md'}]:[]};
    setTimeout(()=>listeners.forEach(fn=>fn({...request,ok:true,result})),10);
}};
const invoke=async request=>{
    if(request.action==='open'){signedIn=true;return {opened:true};}
    if(request.action==='disconnect'){signedIn=false;return {disconnected:true};}
    if(request.action==='status')return {origin:'https://vaos.example',sessionPresent:signedIn};
    return signedIn?{ok:true,answer:'Source evidence HOLD. <img src=x onerror=alert(1)>',sourceSystem:'VAOS_ADAPTIVE',status:'HOLD'}:{ok:false,message:'Sign in to VAOS first.'};
};
createRoot(document.getElementById('root')).render(<JarvisPanel invoke={invoke} onClose={()=>{}} socket={socket} project="fixture"/>);
