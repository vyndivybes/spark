const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const {EventEmitter} = require('node:events');

async function startup(source) {
    let windows=0, backendSpawns=0;
    const app = new EventEmitter();
    Object.assign(app, {requestSingleInstanceLock:()=>true, quit(){}, commandLine:{appendSwitch(){}},
        whenReady:()=>Promise.resolve(), getPath:()=>'/isolated', isPackaged:false});
    class Window extends EventEmitter {
        constructor(){super();windows++; this.webContents={id:1};}
        loadFile(){return new Promise(()=>{});}
    }
    const modules = {
        electron:{app,BrowserWindow:Window,ipcMain:{handle(){},on(){}},session:{},shell:{},dialog:{},clipboard:{}},
        './experience-manager.cjs':{createExperienceManager:()=>({})},
        './jarvis-bridge.cjs':{createJarvisBridge:()=>({listen:async()=> 'http://isolated'})},
        './business-portals.cjs':{createBusinessPortals:()=>({})},
        './workspace-auth.cjs':{trustedWorkspaceSender:()=>false},
        './rea-evidence.cjs':{},
        './brain-display.cjs':{readBrainDisplay:async()=>({nodes:[],edges:[]})},
        net:{createServer:()=>{const server=new EventEmitter();server.listen=()=>{queueMicrotask(()=>server.emit('listening'));};server.close=()=>{};return server;}},
        http:{get:()=>{const req=new EventEmitter();req.setTimeout=()=>{};queueMicrotask(()=>req.emit('error',Error('Offline')));return req;}},
        child_process:{spawn:()=>{backendSpawns++;return Object.assign(new EventEmitter(),{stdout:new EventEmitter(),stderr:new EventEmitter()});}},
    };
    vm.runInNewContext(source,{require:name=>modules[name]??require(name),__dirname:path.resolve(__dirname,'../electron'),
        process:{env:{NODE_ENV:'production'},platform:'win32',resourcesPath:'/isolated'},
        console:{log(){},warn(){},error(){}},setTimeout:()=>0,queueMicrotask});
    await new Promise(resolve=>setImmediate(resolve));
    return {windows,backendSpawns};
}

test('cockpit is created while backend health stays offline',async()=>{
    const result=await startup(fs.readFileSync(path.join(__dirname,'../electron/main.js'),'utf8'));
    assert.equal(result.windows,1,'An unavailable backend must not delay creating the cockpit');
    assert.equal(result.backendSpawns,1,'Core still starts in parallel with the cockpit');
});
