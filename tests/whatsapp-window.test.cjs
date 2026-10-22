const test=require('node:test');
const assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const {createWhatsAppWindow,whatsappUserAgent}=require('../electron/whatsapp-window.cjs');

test('WhatsApp opens the official site in an isolated persistent window and blocks unrelated navigation',async()=>{
  const instances=[];
  class Window extends EventEmitter {
    constructor(options){super();this.options=options;this.webContents=new EventEmitter();
      this.webContents.getURL=()=>this.url;
      this.webContents.executeJavaScript=async script=>{this.statusScript=script;return this.state||'connected';};
      this.webContents.getUserAgent=()=> 'Mozilla/5.0 spark/1.0.0 Chrome/120.0.0.0 Electron/28.2.0 Safari/537.36';
      this.webContents.setUserAgent=ua=>{this.userAgent=ua;};
      this.webContents.setWindowOpenHandler=fn=>{this.popup=fn;};instances.push(this);}
    async loadURL(url){this.url=url;}
    isDestroyed(){return false;}
    isMinimized(){return false;}
    show(){} focus(){} close(){this.emit('closed');}
  }
  const portal=createWhatsAppWindow({BrowserWindow:Window});
  assert.equal((await portal.open()).opened,true);
  const window=instances[0];
  assert.equal(window.url,'https://web.whatsapp.com');
  assert.equal(window.options.webPreferences.partition,'persist:spark-whatsapp');
  assert.equal(window.options.webPreferences.nodeIntegration,false);
  assert.equal(window.options.webPreferences.contextIsolation,true);
  assert.equal(window.options.webPreferences.sandbox,true);
  assert.equal(window.userAgent,'Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36');
  assert.deepEqual(window.popup(),{action:'deny'});
  let blocked=false;
  window.webContents.emit('will-navigate',{preventDefault(){blocked=true;}},'https://example.com/');
  assert.equal(blocked,true);
  assert.equal((await portal.open()).reused,true);
  assert.equal(instances.length,1);
  assert.equal((await portal.status()).state,'connected');
  assert.equal((await portal.status()).sending_enabled,false);
  assert.equal((await portal.status()).phone_identity_verified,false);
  assert.ok(window.statusScript.includes('#pane-side'));
  assert.ok(!window.statusScript.includes('localStorage'));
  window.state='link_required';
  assert.equal((await portal.status()).state,'link_required');
  window.url='https://example.com/';
  assert.equal((await portal.status()).state,'unknown');
  portal.close();
  assert.equal((await portal.open()).reused,false);
});

test('WhatsApp compatibility preserves the actual Chromium version',()=>{
  assert.equal(whatsappUserAgent('Mozilla/5.0 Spark/1.0 Chrome/120.0 Electron/28.0 Safari/537.36'),
    'Mozilla/5.0 Chrome/120.0 Safari/537.36');
});
