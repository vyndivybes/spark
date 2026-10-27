import {useCallback, useEffect, useRef, useState} from 'react';
import {BrowserEchoAudio} from './BrowserEchoAudio.mjs';

export function useStartupBriefing({socket, connected, authenticated, voiceRequested}) {
  const [status, setStatus] = useState({state:'waiting', message:'Spark will read your welcome, weather, and Morning Digest when the core is ready.'});
  const attempted = useRef(false);
  const current = useRef(null);
  const bridge = useRef(null);
  const drain = useRef(null);
  const cleanup = useCallback(() => {
    clearInterval(drain.current); drain.current = null;
    bridge.current?.stop(); bridge.current = null;
  }, []);
  const stop = useCallback(() => {
    current.current = null;
    socket.emit('stop_startup_briefing'); cleanup();
    setStatus({state:'cancelled', message:'Startup briefing stopped.'});
  }, [socket, cleanup]);
  const play = useCallback(async () => {
    if (!connected || !authenticated || voiceRequested || bridge.current) return;
    attempted.current = true;
    const id = crypto.randomUUID();
    current.current = id;
    setStatus({state:'preparing',message:'Preparing your welcome, Coimbatore weather, and today’s Morning Digest…'});
    const listeners = new Map();
    const adapter = {
      on: (_, listener) => {const wrapped = data => {if (data?.id === id && current.current === id) listener(data.pcm);}; listeners.set(listener, wrapped); socket.on('startup_briefing_audio', wrapped);},
      off: (_, listener) => {const wrapped = listeners.get(listener); if (wrapped) socket.off('startup_briefing_audio', wrapped); listeners.delete(listener);},
    };
    const output = new BrowserEchoAudio({socket:adapter,
      onError: message => {stop(); setStatus({state:'error',message});},
      onWarning: message => setStatus(previous => ({...previous,message})),
    });
    output.maxPendingSeconds = 180;
    bridge.current = output;
    try {
      await output.start({playbackOnly:true,outputId:localStorage.getItem('selectedSpeakerId') || ''});
      if (current.current !== id) {output.stop(); return;}
      const city = localStorage.getItem('spark-weather-city') || 'Coimbatore';
      socket.timeout(10000).emit('startup_briefing', {id,city,workspace_token:socket.workspaceToken}, (error,result) => {
        if (current.current !== id) return;
        if (error || !result?.ok) {cleanup(); setStatus({state:'error',message:result?.message || 'Spark startup voice is unavailable. You can replay when ready.'});}
      });
    } catch (error) {
      if (current.current === id) {cleanup(); setStatus({state:'error',message:error.message || 'Spark speaker could not start.'});}
    }
  }, [socket,connected,authenticated,voiceRequested,cleanup,stop]);
  useEffect(() => {
    const state = data => {
      if (data?.id !== current.current) return;
      if (data.state === 'completed') {
        // Provider generation can finish ahead of the actual speaker clock.
        // Keep the output graph alive until the last queued word has played.
        clearInterval(drain.current);
        drain.current = setInterval(() => {
          const output = bridge.current;
          if (!output || (!output.pendingPcm.length && !output.sources.size)) {
            cleanup(); setStatus({state:'completed',message:'Welcome, weather, and Morning Digest briefing finished.'});
          }
        }, 200);
      } else if (['error','cancelled'].includes(data.state)) {
        cleanup(); setStatus({state:data.state,message:data.message || 'Startup briefing stopped.'});
      } else setStatus({state:data.state,message:data.state === 'speaking' ? 'Spark is reading your startup briefing. Microphone stays muted.' : 'Preparing your welcome, weather, and Morning Digest…'});
    };
    socket.on('startup_briefing_state',state);
    return () => socket.off('startup_briefing_state',state);
  }, [socket,cleanup]);
  useEffect(() => {
    if (!connected || !authenticated || voiceRequested) {if (bridge.current) stop(); return undefined;}
    let tries = 0;
    const timer = setInterval(() => {
      if (attempted.current || ++tries > 40) {clearInterval(timer); return;}
      if (socket.workspaceToken) {clearInterval(timer); play();}
    }, 250);
    return () => clearInterval(timer);
  }, [socket,connected,authenticated,voiceRequested,play,stop]);
  useEffect(() => () => {socket.emit('stop_startup_briefing'); cleanup();}, [socket,cleanup]);
  return {...status, play, stop, active:['preparing','speaking'].includes(status.state)};
}
