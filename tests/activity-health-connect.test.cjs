const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const {pathToFileURL}=require('node:url');
const read=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');
const getParser=()=>import(pathToFileURL(path.resolve(__dirname,'../src/utils/healthConnectSummary.mjs')).href);

test('ARKUS Health Connect shared summaries display correct aggregated data, not Garmin assumptions',async()=>{
 const {parseHealthConnectSummary}=await getParser();
 const raw='Last 7 days\n\nActivities: 3\nSteps: 12,345\nDistance: 56.78 km\n\n'+
    'Source apps: com.garmin.android.apps.connectmobile, com.example.fitness\n\n'+
    'Health Connect totals may include non-Garmin sources.';
 const data=parseHealthConnectSummary(raw);
 assert.deepEqual({period:data.period,activities:data.activities,steps:data.steps,distanceKm:data.distanceKm},
  {period:'Last 7 days',activities:3,steps:12345,distanceKm:56.78});
 assert.ok(data.sources.includes('com.example.fitness'));
 assert.equal(data.origin,'Android Health Connect (user-shared)');
 assert.equal(data.directGarminConnection,false);
 assert.equal(data.verifiedGarminOrigin,false);
});

test('Invalid, oversized, inaccurate and untrusted summary text fails closed',async()=>{
 const {parseHealthConnectSummary}=await getParser();
 for(const raw of ['hello world',
 'Last 7 days\n\nActivities: 3\nSteps: 1\nDistance: NaN km',
 'Last 7 days\n\nActivities: -1\nSteps: 1\nDistance: 12 km',
 'Last 7 days\n\nActivities: 1\nSteps: 2\nDistance: 1.00 km\nGarmin device connected',
 'A'.repeat(15000)]){
  assert.throws(()=>parseHealthConnectSummary(raw));
 }
});

test('ARKUS-ported Android project retains permission-only Health Connect reader',()=>{
 const app=read('android/app/src/main/java/com/spark/companion/MainActivity.kt');
 const manifest=read('android/app/src/main/AndroidManifest.xml');
 const build=read('android/app/build.gradle.kts');
 const gradle=read('android/settings.gradle.kts');
 assert.match(app,/HealthConnectClient\.getOrCreate/);
 assert.match(app,/getGrantedPermissions\(\)/);
 assert.match(app,/ExerciseSessionRecord/);
 assert.match(app,/StepsRecord/);
 assert.match(app,/DistanceRecord/);
 assert.match(app,/ACTION_SEND/);
 assert.match(app,/Copy summary/);
 assert.doesNotMatch(app,/http:|https:|BluetoothGatt|BluetoothSocket|WifiManager/);
 assert.doesNotMatch(manifest,/<uses-permission.*INTERNET/);
 assert.match(manifest,/health.READ_EXERCISE/);
 assert.match(build,/applicationId = "com.spark.companion"/);
 assert.match(gradle,/SPARKAndroid/);
});

test('SPARK cockpit offers real manual Health Connect import and no fake direct pairing',()=>{
 const app=read('src/App.jsx');
 const panel=read('src/components/HealthConnectPanel.jsx');
 assert.match(app,/HealthConnectPanel/);
 assert.match(app,/PHONE \/ WATCH/);
 assert.match(panel,/parseHealthConnectSummary/);
 assert.match(panel,/Paste summary/);
 assert.match(panel,/Not a live Bluetooth pairing/i);
 assert.doesNotMatch(panel,/socket.emit\('pair_garmin'/);
});
