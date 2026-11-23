const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');
test('desktop USB bridge is inaccessible except from owning SPARK cockpit',()=>{
 const main=read('electron/main.js');
 const start=main.indexOf("ipcMain.handle('spark:phone-usb'");
 const end=main.indexOf("ipcMain.handle('spark:workspace-token'",start);
 assert.ok(start>0&&end>start);
 const handler=main.slice(start,end);
 assert.match(handler,/trustedWorkspaceSender\(event,mainWindow/);
 assert.match(handler,/PHONE_USB_COCKPIT_DENIED/);
 assert.match(handler,/\['start','stop','status','take','personal-list'\]/);
 assert.doesNotMatch(handler,/shell\.open|exec\(|spawn\(/);
 assert.match(main,/void phoneUsbBridge\?\.stop\(\)/);
});
test('Android transport is USB-only and never adds general cleartext LAN access',()=>{
 const manifest=read('android/app/src/main/AndroidManifest.xml');
 const network=read('android/app/src/main/res/xml/network_security_config.xml');
 const client=read('android/app/src/main/java/com/spark/companion/UsbBridgeClient.kt');
 assert.match(manifest,/android\.permission\.INTERNET/);
 assert.match(manifest,/networkSecurityConfig="@xml\/network_security_config"/);
 assert.match(network,/<base-config cleartextTrafficPermitted="false"\s*\/>/);
 assert.match(network,/<domain includeSubdomains="false">127\.0\.0\.1<\/domain>/);
 assert.doesNotMatch(network,/0\.0\.0\.0|192\.168/);
 assert.match(client,/BASE_URL \+ path/);
 assert.match(client,/Proxy\.NO_PROXY/);
 assert.doesNotMatch(client,/WebSocket|cloudflare|fetchRemote|Retrofit/);
});
test('Android never sends health summary during pairing or without explicit user tap',()=>{
 const app=read('android/app/src/main/java/com/spark/companion/MainActivity.kt');
 assert.match(app,/UsbBridgeClient\.pair\(code\)/);
 assert.match(app,/setOnClickListener\s*\{[\s\S]*UsbBridgeClient\.sendSummary\(token, next, report\)/);
 assert.match(app,/usbSendButton\.isEnabled = summary != null/);
 assert.match(app,/usbSessionToken = null/);
});
test('desktop panel revokes bridge when closed and parses transfers through existing strict parser',()=>{
 const panel=read('src/components/HealthConnectPanel.jsx');
 assert.match(panel,/ipc\.invoke\('spark:phone-usb',\{action:'take'\}\)/);
 assert.match(panel,/parseHealthConnectSummary\(imported\)/);
 assert.match(panel,/clearInterval\(interval\)/);
 assert.match(panel,/\{action:'stop'\}/);
});
