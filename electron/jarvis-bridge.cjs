'use strict';
const http=require('node:http');
const {timingSafeEqual}=require('node:crypto');

const DEFAULT_ORIGIN='https://vaos.vayushastr.workers.dev';
function jarvisOrigin(value=DEFAULT_ORIGIN){
  const url=new URL(value);
  if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||url.pathname!=='/')throw Error('VAOS must be an HTTPS origin.');
  return url.origin;
}
function validateQuestion(question){
  if(typeof question!=='string'||question.trim().length<5||question.trim().length>300||/[\x00-\x1f\x7f]/.test(question))throw Error('Ask a Jarvis question of 5 to 300 characters.');
  return question.trim();
}
function normalizeReply(payload){
  const data=payload?.data;
  if(!data||data.readOnly!==true||data.advisoryOnly!==true||data.actionAuthorized===true||data.automationExecuted===true||typeof data.answer!=='string'||data.answer.length>16000)throw Error('VAOS returned an unsupported advisory response.');
  return {ok:true,answer:data.answer,sourceSystem:data.sourceSystem||'VAOS',status:String(data.status||'ADVISORY').slice(0,80),
    readOnly:true,advisoryOnly:true,actionAuthorized:false,
    ...(data.sourceCoverage?{sourceCoverage:data.sourceCoverage}:{})};
}

function createJarvisBridge({BrowserWindow,session,token,origin=DEFAULT_ORIGIN,businessRead}){
  origin=jarvisOrigin(origin);
  const portalSession=session.fromPartition('persist:spark-vaos-jarvis');
  let window=null,server=null;
  async function open(){
    if(window&&!window.isDestroyed()){window.show();window.focus();return {opened:true,reused:true};}
    window=new BrowserWindow({width:1360,height:900,title:'SPARK · VAOS Jarvis',backgroundColor:'#07111d',
      webPreferences:{session:portalSession,nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
    const owned=window;
    owned.webContents.setWindowOpenHandler(()=>({action:'deny'}));
    owned.webContents.on('will-navigate',(event,url)=>{if(new URL(url).origin!==origin)event.preventDefault();});
    owned.on('closed',()=>{if(window===owned)window=null;});
    try{await owned.loadURL(origin);}catch{owned.close();throw Error('VAOS could not load. Check the network and portal availability.');}
    return {opened:true,reused:false};
  }
  async function status(){
    const cookies=await portalSession.cookies.get({url:origin,name:'vaos_session'});
    return {configured:true,origin,sessionPresent:cookies.some(c=>!c.expirationDate||c.expirationDate>Date.now()/1000),
      scope:'VAOS advisory reads; authentication is verified on each question.'};
  }
  async function ask(question){
    question=validateQuestion(question);
    if(!(await status()).sessionPresent)return {ok:false,code:'SIGN_IN_REQUIRED',message:'Open VAOS Jarvis and sign in with your founder account, then retry.'};
    const url=new URL('/api/adaptive-intelligence',origin);
    url.searchParams.set('q',question);
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),45000);
    try{
      const response=await portalSession.fetch(url.href,{method:'GET',credentials:'include',redirect:'error',
        headers:{Accept:'application/json'},signal:controller.signal});
      if(!response.ok){
        const messages={401:'VAOS session expired. Open Jarvis and sign in again.',403:'VAOS denied this founder session.',
          409:'VAOS Jarvis advisory intelligence is not commissioned on this deployment.',
          422:'VAOS rejected this question. Ask a bounded advisory question.',429:'VAOS rate limit reached. Retry later.',
          503:'VAOS source evidence or intelligence is unavailable.'};
        return {ok:false,code:'VAOS_HTTP_'+response.status,message:messages[response.status]||'VAOS request failed.'};
      }
      const reader=response.body.getReader();let size=0,chunks=[];
      while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;
        if(size>1_000_000){await reader.cancel();throw Error('VAOS reply exceeds 1 MB.');}chunks.push(Buffer.from(value));}
      return normalizeReply(JSON.parse(Buffer.concat(chunks).toString('utf8')));
    }catch{return {ok:false,code:'VAOS_UNAVAILABLE',message:'VAOS request failed or returned an unsupported reply. Check sign-in and availability.'};}
    finally{clearTimeout(timeout);}
  }
  async function disconnect(){
    if(window&&!window.isDestroyed())window.close();
    await portalSession.clearStorageData();
    return {disconnected:true};
  }
  async function listen(){
    server=http.createServer(async(req,res)=>{
      const provided=Buffer.from(req.headers.authorization||'');const expected=Buffer.from('Bearer '+token);
      const reply=(code,value)=>{res.writeHead(code,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
      if(provided.length!==expected.length||!timingSafeEqual(provided,expected))return reply(403,{ok:false,message:'Unauthorized bridge client.'});
      if(req.method!=='POST'||!['/ask','/business-read'].includes(req.url))return reply(404,{ok:false,message:'Not found.'});
      try{
        let size=0,parts=[];
        for await(const chunk of req){size+=chunk.length;if(size>4096)return reply(413,{ok:false,message:'Request too large.'});parts.push(chunk);}
        const body=JSON.parse(Buffer.concat(parts).toString('utf8'));
        if(req.url==='/business-read'){
          if(!businessRead||!body||Object.keys(body).length!==1||!['vyndi-os','vedm'].includes(body.portal))return reply(400,{ok:false,message:'Select a configured business read.'});
          return reply(200,await businessRead(body.portal));
        }
        return reply(200,await ask(body.question));
      }catch{return reply(400,{ok:false,message:'Invalid Jarvis request.'});}
    });
    server.requestTimeout=10000;
    await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
    return 'http://127.0.0.1:'+server.address().port;
  }
  function close(){if(window&&!window.isDestroyed())window.close();server?.closeAllConnections();server?.close();}
  return {open,status,ask,disconnect,listen,close};
}
module.exports={createJarvisBridge,jarvisOrigin,validateQuestion,normalizeReply,DEFAULT_ORIGIN};
