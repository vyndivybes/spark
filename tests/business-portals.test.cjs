const test = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const {createBusinessPortals, PORTALS} = require('../electron/business-portals.cjs');

function libraryWindow(value,origin='https://vedm.vayushastr.workers.dev/'){
  return class Window extends EventEmitter{
    constructor(options){super();assert.equal(options.show,false);this.webContents=new EventEmitter();
      this.webContents.setWindowOpenHandler=()=>{};
      this.webContents.getURL=()=>origin;
      this.webContents.executeJavaScript=async script=>{
        assert.ok(script.includes('window.VEDM_LIBRARY'));
        assert.ok(!script.includes('cookie'));
        return value;
      };
    }
    async loadURL(){} isDestroyed(){return false;} close(){} show(){} focus(){}
  };
}

test('business reads preserve source limits and use the final published library state',async()=>{
  const calls=[];
  const data={issuedAt:'2026-09-28',authority:{geometry:'E-K75'},configurations:[],gates:[],navigation:[]};
  const portals=createBusinessPortals({BrowserWindow:libraryWindow(JSON.stringify(data)),session:{fromPartition:partition=>({
    fetch:async(url,init)=>{calls.push({partition,url,init});return new Response(JSON.stringify({ok:true,
      authorityByDomain:{geometry:{id:'E-K75'}},releaseReady:false,actor:{userId:'private'}}));}
  })}});
  const authority=await portals.read('vyndi-os');
  assert.equal(authority.ok,true);assert.equal(authority.sourceKind,'seeded-authority-reference');
  assert.equal(authority.data.releaseReady,false);assert.equal(authority.data.actor,undefined);
  const library=await portals.read('vedm');
  assert.equal(library.ok,true);assert.equal(library.data.issuedAt,'2026-09-28');
  assert.equal(library.sourceKind,'published-engineering-library');
  await assert.rejects(portals.read('https://example.com'));
  assert.equal(calls.length,1);
  assert.equal(calls[0].url,'https://vyndios.vayushastr.workers.dev/api/engineering/authority');
  assert.equal(calls[0].init.method,'GET');assert.equal(calls[0].init.redirect,'error');
  assert.equal(calls[0].init.credentials,'include');
});

test('business reads reject expired sessions, unexpected library origins and oversized data',async()=>{
  let response=new Response('private error',{status:401});
  const session={fromPartition:()=>({fetch:async()=>response})};
  const portals=createBusinessPortals({BrowserWindow:libraryWindow('{}','https://example.com'),session});
  assert.equal((await portals.read('vyndi-os')).code,'SIGN_IN_REQUIRED');
  assert.equal((await portals.read('vedm')).ok,false);
  const large=createBusinessPortals({BrowserWindow:libraryWindow('x'.repeat(1_000_001)),session});
  assert.equal((await large.read('vedm')).ok,false);
  response=new Response('x'.repeat(1_000_001));
  assert.equal((await portals.read('vyndi-os')).ok,false);
});

test('business portals reuse isolated windows and deny arbitrary destinations', async () => {
  const created = [], partitions = [];
  class Window extends EventEmitter {
    constructor(options) {
      super(); this.options = options; this.webContents = new EventEmitter();
      this.webContents.setWindowOpenHandler = handler => {this.popup = handler;};
      created.push(this);
    }
    async loadURL(url) {this.url = url;}
    isDestroyed() {return false;}
    show() {} focus() {}
    close() {this.emit('closed');}
  }
  const portals = createBusinessPortals({BrowserWindow:Window,
    session:{fromPartition:partition => {partitions.push(partition); return {partition};}}});
  await assert.rejects(portals.open('https://example.com'));
  await assert.rejects(portals.open('__proto__'));
  assert.equal(created.length, 0);
  assert.equal((await portals.open('vyndi-os')).scope, 'portal-only');
  assert.equal((await portals.open('vyndi-os')).reused, true);
  await portals.open('vedm');
  assert.deepEqual(partitions, ['persist:spark-vyndi-os', 'persist:spark-vedm']);
  for (const window of created) {
    assert.equal(window.options.webPreferences.nodeIntegration, false);
    assert.equal(window.options.webPreferences.contextIsolation, true);
    assert.equal(window.options.webPreferences.sandbox, true);
    assert.deepEqual(window.popup(), {action:'deny'});
    let prevented = false;
    window.webContents.emit('will-navigate', {preventDefault:() => {prevented = true;}}, 'https://example.com');
    assert.equal(prevented, true);
  }
  assert.equal(created[0].url, PORTALS['vyndi-os'].origin);
  portals.close();
  assert.equal((await portals.open('vedm')).reused, false);
  portals.close();
});
