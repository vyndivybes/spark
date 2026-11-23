'use strict';
// Personal, physical-USB-only preview. No LAN listener, cloud storage,
// reverse control, background sync, or business-operation permissions.
const http=require('node:http');
const {randomInt,randomBytes,timingSafeEqual}=require('node:crypto');
const PAIRING_MS=120000;
const SESSION_MS=600000;
const MAX_BODY=6000;

const HEALTH_SUMMARY=/^Last 7 days\n\nActivities: (\d{1,7})\nSteps: (?:\d{1,3}(?:,\d{3})*|\d{1,10})\nDistance: \d{1,8}(?:\.\d{1,2})? km\n\n(?:(?:Source apps: [a-zA-Z0-9._,\s-]+)|(?:No activity-session sources found))(?:\nShowing first 100 activities\.)?\n\nHealth Connect totals may include non-Garmin sources\.$/;
function validSummary(text){
 if(typeof text!=='string'||text.length<45||text.length>4000)return false;
 const m=HEALTH_SUMMARY.exec(text);
 return Boolean(m&&Number(m[1])<=100000);
}
function matchesSecret(value,expected){
 if(typeof value!=='string'||typeof expected!=='string')return false;
 const a=Buffer.from(value),b=Buffer.from(expected);
 return a.length===b.length&&timingSafeEqual(a,b);
}
function createPhoneUsbBridge({
 port=38177,now=Date.now,
 generateCode=()=>String(randomInt(0,100000000)).padStart(8,'0'),
 generateToken=()=>randomBytes(32).toString('hex'),
 mobileChat=null
}={}){
 if(!Number.isInteger(port)||port<0||port>65535)throw Error('PHONE_USB_PORT_INVALID');
 let server=null,code=null,deadline=0,token=null,pairedUntil=0,
  badAttempts=0,lastSequence=0,pending=null,actualPort=null,
  aiEnabled=false,chatBusy=false,conversation=[];
 function state(){
  return {listening:Boolean(server),host:'127.0.0.1',
   port:actualPort,code:server&&!token&&now()<deadline?code:null,
   expiresAt:deadline,paired:Boolean(token&&now()<pairedUntil),
   pending:Boolean(pending),aiEnabled};
 }
 function reply(res,status,message){
  res.writeHead(status,{'Content-Type':'application/json; charset=utf-8',
   'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});
  res.end(JSON.stringify(message));
 }
 async function receive(req){
  const claimed=Number(req.headers['content-length']||'0');
  if(claimed>MAX_BODY)throw Error('PAYLOAD_TOO_LARGE');
  let bytes=0;const chunks=[];
  for await(const chunk of req){
   bytes+=chunk.length;
   if(bytes>MAX_BODY)throw Error('PAYLOAD_TOO_LARGE');
   chunks.push(chunk);
  }
  try{
   return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  }catch{throw Error('JSON_INVALID');}
 }
 async function handle(req,res){
  const url=req.url,host='127.0.0.1:'+actualPort;
  if(req.method!=='POST'||!['/pair','/summary','/mobile-chat'].includes(url))
   return reply(res,405,{ok:false,code:'METHOD_NOT_ALLOWED'});
  if(req.headers.host!==host||req.headers.origin||
     req.socket.remoteAddress!=='127.0.0.1')
   return reply(res,403,{ok:false,code:'LOCAL_USB_ONLY'});
  if(!/^application\/json(?:;|$)/i.test(req.headers['content-type']||''))
   return reply(res,415,{ok:false,code:'JSON_REQUIRED'});
  let body;
  try{body=await receive(req)}
  catch(e){return reply(res,e.message==='PAYLOAD_TOO_LARGE'?413:400,
   {ok:false,code:e.message==='PAYLOAD_TOO_LARGE'?'PAYLOAD_TOO_LARGE':'JSON_INVALID'});}
  if(!body||typeof body!=='object'||Array.isArray(body))
   return reply(res,422,{ok:false,code:'INVALID_INPUT'});
  if(url==='/pair'){
   if(token)return reply(res,409,{ok:false,code:'ALREADY_PAIRED'});
   if(now()>=deadline)return reply(res,410,{ok:false,code:'CODE_EXPIRED'});
   if(badAttempts>=5)return reply(res,429,{ok:false,code:'PAIRING_LOCKED'});
   if(Object.keys(body).length!==1||!matchesSecret(body.code,code)){
    badAttempts++;
    return reply(res,badAttempts>=5?429:403,{ok:false,code:'PAIRING_DENIED'});
   }
   token=generateToken();
   if(!/^[a-f0-9]{64}$/.test(token))throw Error('PHONE_USB_TOKEN_INVALID');
   code=null;pairedUntil=now()+SESSION_MS;
   return reply(res,200,{ok:true,sessionToken:token,expiresInSeconds:SESSION_MS/1000});
  }
  const auth=req.headers.authorization||'';
  if(!token||!matchesSecret(auth,'Bearer '+token))
   return reply(res,403,{ok:false,code:'SESSION_DENIED'});
  if(now()>=pairedUntil)return reply(res,410,{ok:false,code:'SESSION_EXPIRED'});
  if(url==='/mobile-chat'){
   if(!aiEnabled||typeof mobileChat!=='function')
    return reply(res,403,{ok:false,code:'AI_DISABLED'});
   if(Object.keys(body).sort().join(',')!=='prompt,sequence'||
      !Number.isSafeInteger(body.sequence)||body.sequence<1||
      body.sequence>1000000||typeof body.prompt!=='string'||
      body.prompt.trim().length<3||body.prompt.length>400||
      /[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f]/.test(body.prompt))
    return reply(res,422,{ok:false,code:'PROMPT_INVALID'});
   if(body.sequence!==lastSequence+1)
    return reply(res,409,{ok:false,code:'SEQUENCE_REJECTED'});
   if(chatBusy)return reply(res,409,{ok:false,code:'AI_BUSY'});
   chatBusy=true;
   const session=token;
   try{
    const output=await mobileChat({prompt:body.prompt.trim(),history:conversation.slice(-6)});
    if(!aiEnabled||token!==session||now()>=pairedUntil)
     return reply(res,403,{ok:false,code:'AI_SESSION_REVOKED'});
    if(!output||typeof output!=='object'||Array.isArray(output)||
       Object.keys(output).sort().join(',')!=='answer,provider'||
       !['gemini','groq'].includes(output.provider)||
       typeof output.answer!=='string'||output.answer.trim().length<1||
       output.answer.length>2800)
     return reply(res,503,{ok:false,code:'AI_PROVIDER_UNAVAILABLE'});
    const answer=output.answer.trim();
    conversation.push({role:'user',content:body.prompt.trim()},
                      {role:'assistant',content:answer.slice(0,1000)});
    conversation=conversation.slice(-6);
    lastSequence=body.sequence;
    return reply(res,200,{ok:true,answer,provider:output.provider,
                          advisoryOnly:true,sequence:lastSequence});
   }catch{
    return reply(res,503,{ok:false,code:'AI_PROVIDER_UNAVAILABLE'});
   }finally{chatBusy=false;}
  }
  if(Object.keys(body).sort().join(',')!=='sequence,summary'||
     !Number.isSafeInteger(body.sequence)||body.sequence<1||
     body.sequence>1000000||!validSummary(body.summary))
   return reply(res,422,{ok:false,code:'SUMMARY_INVALID'});
  if(body.sequence!==lastSequence+1)return reply(res,409,{ok:false,code:'SEQUENCE_REJECTED'});
  if(pending!==null)return reply(res,409,{ok:false,code:'SUMMARY_UNREAD'});
  pending=body.summary;lastSequence=body.sequence;
  return reply(res,200,{ok:true,received:true,sequence:lastSequence});
 }
 return Object.freeze({
  status:state,
  async start(){
   if(server)return state();
   code=generateCode();
   if(!/^[0-9]{8}$/.test(code))throw Error('PHONE_USB_CODE_INVALID');
   deadline=now()+PAIRING_MS;badAttempts=0;token=null;pairedUntil=0;
   lastSequence=0;pending=null;aiEnabled=false;chatBusy=false;conversation=[];
   const fresh=http.createServer((req,res)=>void handle(req,res).catch(()=>
    !res.headersSent?reply(res,503,{ok:false,code:'USB_TRANSFER_FAILED'}):res.end()));
   fresh.requestTimeout=10000;
   fresh.headersTimeout=10000;
   fresh.maxRequestsPerSocket=64;
   try{
    await new Promise((resolve,reject)=>{
     fresh.once('error',reject);
     fresh.listen(port,'127.0.0.1',resolve);
    });
   }catch(e){fresh.close();code=null;throw Error('PHONE_USB_LISTEN_FAILED');}
   server=fresh;actualPort=fresh.address().port;
   return state();
  },
  take(){const value=pending;pending=null;return value;},
  setAiEnabled(enabled){
   if(typeof enabled!=='boolean')throw Error('PHONE_USB_AI_PERMISSION_INVALID');
   if(!server)throw Error('PHONE_USB_NOT_RUNNING');
   aiEnabled=enabled;
   if(!enabled){conversation=[];}
   return state();
  },
  async stop(){
   const existing=server;server=null;
   code=null;token=null;deadline=0;pairedUntil=0;
   badAttempts=0;lastSequence=0;pending=null;actualPort=null;
   aiEnabled=false;chatBusy=false;conversation=[];
   if(existing){
    existing.closeAllConnections();
    await new Promise(resolve=>existing.close(resolve));
   }
   return {stopped:true};
  },
 });
}
module.exports={createPhoneUsbBridge,validSummary};
