const path=require('node:path');
const {fileURLToPath}=require('node:url');
function trustedWorkspaceSender(event,window,entry,isDev){
    if(!window||event.sender!==window.webContents||event.senderFrame!==window.webContents.mainFrame)return false;
    try{
        const url=new URL(event.senderFrame.url);
        if(isDev&&['http://localhost:5173','http://127.0.0.1:5173'].includes(url.origin))return true;
        if(url.protocol==='file:'){url.search='';url.hash='';return path.resolve(fileURLToPath(url))===path.resolve(entry);}
        return false;
    }catch{return false;}
}
module.exports={trustedWorkspaceSender};
