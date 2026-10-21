'use strict';

const PORTALS = Object.freeze({
  'vyndi-os': {name:'VYNDI OS', origin:'https://vyndios.vayushastr.workers.dev'},
  vedm: {name:'VEDM', origin:'https://vedm.vayushastr.workers.dev'},
});

function createBusinessPortals({BrowserWindow, session}) {
  const windows = new Map();
  async function read(id) {
    if (!Object.hasOwn(PORTALS,id)) throw Error('Select a configured business portal.');
    const origin=PORTALS[id].origin;
    const sourceUrl=origin+(id==='vyndi-os'?'/api/engineering/authority':'/');
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),20000);
    try {
      if(id==='vedm'){
        const expired=new Promise((_,reject)=>controller.signal.addEventListener('abort',()=>reject(Error('Read timed out.')),{once:true}));
        if(!windows.get(id)||windows.get(id).isDestroyed())await Promise.race([open(id,{show:false}),expired]);
        const contents=windows.get(id).webContents;
        if(new URL(contents.getURL()).origin!==origin)throw Error('Unexpected library origin.');
        // Read the final published state after the portal has applied its overlays.
        // Fixed projection only: no caller-supplied script, URL, cookie or DOM mutation.
        const raw=await Promise.race([contents.executeJavaScript("JSON.stringify((({issuedAt,repository,authority,configurations,gates,navigation})=>({issuedAt,repository,authority,configurations,gates,navigation}))(window.VEDM_LIBRARY))"),expired]);
        if(typeof raw!=='string'||Buffer.byteLength(raw)>1_000_000)throw Error('Invalid library response.');
        const data=JSON.parse(raw);
        if(typeof data.issuedAt!=='string'||!data.authority||!Array.isArray(data.configurations)||!Array.isArray(data.gates))throw Error('Unsupported library schema.');
        return {ok:true,readOnly:true,sourceSystem:'VEDM',sourceKind:'published-engineering-library',sourceUrl,
          limitation:'Published engineering reference; preserve development, superseded and release holds. No synchronization or release authority.',data};
      }
      const response=await session.fromPartition(`persist:spark-${id}`).fetch(sourceUrl,{
        method:'GET',credentials:'include',redirect:'error',signal:controller.signal,
        headers:{Accept:id==='vyndi-os'?'application/json':'text/javascript'}});
      if (!response.ok) return {ok:false,code:[401,403].includes(response.status)?'SIGN_IN_REQUIRED':'SOURCE_UNAVAILABLE',
        message:`${PORTALS[id].name} read failed. Check portal sign-in and source availability.`};
      const reader=response.body.getReader();let size=0;const parts=[];
      while(true){const {done,value}=await reader.read();if(done)break;
        size+=value.length;if(size>1_000_000){await reader.cancel();throw Error('Source limit exceeded.');}
        parts.push(Buffer.from(value));}
      const text=Buffer.concat(parts).toString('utf8');
      const source=JSON.parse(text);
      if(source.ok!==true||typeof source.authorityByDomain!=='object'||!source.authorityByDomain||typeof source.releaseReady!=='boolean')throw Error('Unsupported authority source.');
      const keys=['schema','sourceRepository','sourceCommit','asOfDate','valid','releaseReady','authorityByDomain','blockingGateIds','issues','mutationAuthority'];
      const sourceKind='seeded-authority-reference';
      const limitation='Authenticated reference graph built from a seed; not a live business ledger or production release approval.';
      return {ok:true,readOnly:true,sourceSystem:PORTALS[id].name,sourceKind,sourceUrl,limitation,
        data:Object.fromEntries(keys.filter(key=>Object.hasOwn(source,key)).map(key=>[key,source[key]]))};
    }catch{return {ok:false,code:'SOURCE_UNAVAILABLE',message:'Source read failed or returned an unsupported schema. Check the portal and retry.'};}
    finally{clearTimeout(timeout);}
  }
  async function open(id,{show=true}={}) {
    if (!Object.hasOwn(PORTALS, id)) throw Error('Select a configured business portal.');
    const portal = PORTALS[id];
    const existing = windows.get(id);
    if (existing && !existing.isDestroyed()) {
      if(show){existing.show(); existing.focus();}
      return {opened:true, reused:true, name:portal.name, scope:'portal-only'};
    }
    const window = new BrowserWindow({width:1360, height:900, show, title:`SPARK · ${portal.name}`,
      webPreferences:{session:session.fromPartition(`persist:spark-${id}`),
        nodeIntegration:false, contextIsolation:true, sandbox:true, webSecurity:true}});
    windows.set(id, window);
    window.webContents.setWindowOpenHandler(() => ({action:'deny'}));
    window.webContents.on('will-navigate', (event, url) => {
      try { if (new URL(url).origin !== portal.origin) event.preventDefault(); }
      catch { event.preventDefault(); }
    });
    window.on('closed', () => {if (windows.get(id) === window) windows.delete(id);});
    try { await window.loadURL(portal.origin); }
    catch { window.close(); throw Error(`${portal.name} could not load. Check portal availability.`); }
    return {opened:true, reused:false, name:portal.name, scope:'portal-only'};
  }
  function close() {for (const window of windows.values()) if (!window.isDestroyed()) window.close();}
  return {open, read, close};
}

module.exports = {PORTALS, createBusinessPortals};
