import React,{useEffect,useRef,useState} from 'react';
const labels={review_required:'Review package and API access',generated:'Candidate ready for review',tested:'Expected examples passed',rejected:'Tests failed',repairing:'Repairing generated source',registering:'Registering tested tool',generating:'Inventing a Python tool',testing:'Testing expected results',registered:'New tool registered',running:'Executing tool',completed:'Execution complete',failed:'Tool failed',inspect:'Inspecting source',test:'Checking source repair',verify:'Source upgrade verified',risk_check:'Review required',monitor:'Checking upgrade health'};
export default function EvolutionActivity({socket}){
 const [activity,setActivity]=useState(null);const [energy,setEnergy]=useState(0);const timer=useRef();
 useEffect(()=>{
  const level=data=>setEnergy(Math.max(0,Math.min(1,(Number(data?.value)||0)/255)));
  const transcript=data=>{if(data?.text){window.sparkVoicePulse?.();setEnergy(0.7);}};
  const progress=data=>{setActivity(data);clearTimeout(timer.current);timer.current=setTimeout(()=>setActivity(null),['completed','failed','registered','verify'].includes(data.phase)?8000:90000);};
  socket?.on('generated_tool_progress',progress);socket?.on('audio_level',level);socket?.on('transcription',transcript);
  return()=>{socket?.off('generated_tool_progress',progress);socket?.off('audio_level',level);socket?.off('transcription',transcript);clearTimeout(timer.current);};
 },[socket]);
 return <>
  <div className="spark-voice-glow" aria-hidden="true" style={{'--voice-energy':energy}}/>
  {activity&&<aside className={`spark-evolution-hud ${activity.phase==='failed'?'is-failed':''}`} role="status" aria-live="polite">
   <span className="spark-evolution-orb"/><div><strong>{labels[activity.phase]||'Evolution activity'}</strong><p>{activity.name||activity.project||'Spark'}</p><small>Live runtime event · {activity.phase}</small></div>
   <button aria-label="Dismiss evolution activity" onClick={()=>setActivity(null)}>×</button>
  </aside>}
 </>;
}
