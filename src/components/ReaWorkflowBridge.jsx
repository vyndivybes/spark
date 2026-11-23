import {useEffect} from 'react';
export default function ReaWorkflowBridge({socket}){
 useEffect(()=>{
  const run=async(data,ack)=>{
   if(typeof ack!=='function')return;
   try{
    if(!data||!['test','open'].includes(data.action))throw Error('Invalid preview operation.');
    const ipc=window.require?.('electron')?.ipcRenderer;
    if(!ipc)throw Error('Open the SPARK desktop app for previews.');
    const result=await ipc.invoke('spark:rea-preview',{action:data.action,project:data.project,id:data.id});
    ack({ok:true,state:result?.state,checkCount:Array.isArray(result?.checks)?result.checks.length:0});
   }catch{ack({ok:false});}
  };
  socket?.on('rea_workflow_preview',run);return()=>socket?.off('rea_workflow_preview',run);
 },[socket]);
 return null;
}
