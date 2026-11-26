const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');

test('personal sync stays confined to owner verified desktop cockpit and app-private storage',()=>{
 const main=read('electron/main.js');
 const panel=read('src/components/HealthConnectPanel.jsx');
 const store=read('electron/mobile-personal-sync.cjs');
 assert.match(main,/trustedWorkspaceSender\(event,mainWindow/);
 assert.match(main,/\['set-ai','set-sync','set-control'\]\.includes\(request\.action\)/);
 assert.match(main,/createMobilePersonalStore\(path\.join\(app\.getPath\('userData'\),'mobile-personal'\)\)/);
 assert.match(main,/mobileSync:records=>personalMobileStore\.merge\(records\)/);
 assert.match(panel,/action:'set-sync'/);
 assert.match(panel,/Enable personal notes\/tasks sync/);
 assert.match(main,/case 'personal-list':return personalMobileStore\.read\(\)/);
 assert.match(panel,/action:'personal-list'/);
 assert.match(panel,/Review saved personal notes &amp; tasks/);
 assert.match(panel,/action:'stop'/);
 assert.match(store,/open\(name,'wx',0o600\)/);
 assert.match(store,/await fs\.rename\(name,file\)/);
 assert.doesNotMatch(store,/https?:|fetch\(|axios|cloudflare|send_email|purchase_order/);
});

test('Android personal sync has an explicit user-triggered button and no silent background relay',()=>{
 const ui=read('android/app/src/main/java/com/spark/companion/SparkAiLinkActivity.kt');
 const client=read('android/app/src/main/java/com/spark/companion/UsbBridgeClient.kt');
 const prefs=read('android/app/src/main/java/com/spark/companion/MobilePreferencesStore.kt');
 assert.match(ui,/sync = button\("SYNC PERSONAL NOTES \/ TASKS"\)/);
 assert.match(ui,/UsbBridgeClient\.syncPersonal\(session, next, local\)/);
 assert.match(ui,/mobileStore\.applyPersonalSync\(merged\)/);
 assert.match(client,/post\("\/mobile-sync", outgoing, token\)/);
 assert.match(client,/setOf\("ok", "personalOnly", "records", "sequence"\)/);
 assert.match(prefs,/prefs\.edit\(\)\.putString\("notes", notesJson\.toString\(\)\)/);
 assert.match(prefs,/\.putString\("tasks", tasksJson\.toString\(\)\)\.commit\(\)/);
 assert.doesNotMatch(ui,/autoSync|PeriodicWorkRequest|WorkManager|GROQ_API_KEY|GEMINI_API_KEY/);
});
