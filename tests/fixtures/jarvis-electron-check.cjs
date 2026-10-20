// Real installed Electron check: Chromium fetch includes the isolated session cookie.
const {app,session}=require('electron');
const http=require('node:http');
const assert=require('node:assert/strict');
app.whenReady().then(async()=>{
    const server=http.createServer((req,res)=>{res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({cookie:req.headers.cookie||''}));});
    try{
        await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
        const url='http://127.0.0.1:'+server.address().port;
        const isolated=session.fromPartition('spark-jarvis-cookie-acceptance');
        await isolated.cookies.set({url,name:'vaos_session',value:'synthetic-acceptance',sameSite:'strict'});
        const response=await isolated.fetch(url,{credentials:'include',redirect:'error'});
        const data=await response.json();
        assert.equal(data.cookie,'vaos_session=synthetic-acceptance');
        await isolated.clearStorageData();
        console.log('PASS: installed Electron sends isolated SameSite=Strict session cookies.');
        app.exit(0);
    }catch(error){console.error(error.message);app.exit(1);}
    finally{server.close();}
});
