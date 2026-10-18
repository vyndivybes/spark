/* SPARK Focus — a conservative clock-only Pomodoro workflow.
 * Inspired by ARKUS focus UX, but intentionally avoids unconsented desktop
 * sensors, inferred attention scores, disk logs, camera or background agents.
 * The timer stays active when its UI is collapsed, but does not survive an
 * application restart. Uses wall-clock timestamps, not interval tick counts.
 */
const MIN_MINUTES=1;
const MAX_MINUTES=240;
function durationSeconds(minutes){
  if(typeof minutes!=='number'||!Number.isInteger(minutes)||
     minutes<MIN_MINUTES || minutes>MAX_MINUTES)
    throw new RangeError('Choose a whole number of minutes from 1 to 240.');
  return minutes*60;
}
function asTime(now){
  if(typeof now!=='number'||!Number.isFinite(now)||now<0)
    throw new TypeError('A nonnegative clock timestamp is required.');
  return now;
}
export function createFocusState(minutes=25){
  const seconds=durationSeconds(minutes);
  return Object.freeze({
    phase:'idle',durationSeconds:seconds,remainingSeconds:seconds,
    deadlineMs:null,startedAtMs:null,completedAtMs:null,
    observationMode:'timer_only',onTargetPercent:null
  });
}
export function remainingSeconds(state, nowMs=Date.now()){
  asTime(nowMs);
  if(!state || typeof state!=='object')throw new TypeError('Invalid focus session');
  if(state.phase==='running'){
    return Math.max(0,Math.ceil((state.deadlineMs-nowMs)/1000));
  }
  return state.remainingSeconds;
}
export function advanceFocus(state, action, nowMs=Date.now()){
  asTime(nowMs);
  if(!state||!action||typeof action.type!=='string')
    throw new TypeError('Invalid focus event');
  switch(action.type){
    case 'start':{
      if(state.phase==='running'||state.phase==='paused')return state;
      const seconds=durationSeconds(action.minutes??(state.durationSeconds/60));
      return Object.freeze({...createFocusState(seconds/60),
        phase:'running',deadlineMs:nowMs+seconds*1000,startedAtMs:nowMs
      });
    }
    case 'tick':{
      if(state.phase!=='running')return state;
      const remaining=remainingSeconds(state,nowMs);
      if(remaining===0)return Object.freeze({
        ...state,phase:'completed',remainingSeconds:0,deadlineMs:null,
        completedAtMs:nowMs
      });
      return remaining===state.remainingSeconds?state:
        Object.freeze({...state,remainingSeconds:remaining});
    }
    case 'pause':{
      if(state.phase!=='running')return state;
      const remaining=remainingSeconds(state,nowMs);
      if(remaining===0)return advanceFocus(state,{type:'tick'},nowMs);
      return Object.freeze({...state,phase:'paused',remainingSeconds:remaining,deadlineMs:null});
    }
    case 'resume':{
      if(state.phase!=='paused')return state;
      return Object.freeze({...state,phase:'running',
        deadlineMs:nowMs+state.remainingSeconds*1000});
    }
    case 'extend':{
      if(state.phase!=='running'&&state.phase!=='paused')return state;
      const additional=durationSeconds(action.minutes);
      // Never exceed a single four-hour session.
      if(state.durationSeconds+additional>MAX_MINUTES*60)
        throw new RangeError('A focus session cannot exceed 240 minutes.');
      return Object.freeze({...state,durationSeconds:state.durationSeconds+additional,
        remainingSeconds:remainingSeconds(state,nowMs)+additional,
        deadlineMs:state.phase==='running'?state.deadlineMs+additional*1000:null});
    }
    case 'reset':return createFocusState(state.durationSeconds/60);
    default:return state;
  }
}
export function formatFocusClock(seconds){
  const value=Number.isFinite(seconds)?Math.max(0,Math.floor(seconds)):0;
  return String(Math.floor(value/60)).padStart(2,'0')+':'+
    String(value%60).padStart(2,'0');
}
