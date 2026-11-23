const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=part=>fs.readFileSync(path.resolve(__dirname,'..',part),'utf8');

test('standalone SPARK Mobile is Android launcher and preserves Health Connect alias',()=>{
 const manifest=read('android/app/src/main/AndroidManifest.xml');
 assert.match(manifest,/android:label="SPARK Mobile"/);
 assert.match(manifest,/<activity android:name="\.SparkMobileActivity" android:exported="true">[\s\S]*?android.intent.action.MAIN/);
 assert.match(manifest,/<activity android:name="\.MainActivity" android:exported="false"/);
 assert.match(manifest,/android:name="\.HealthPermissionUsageActivity"[\s\S]*?android:targetActivity="\.MainActivity"/);
 assert.match(manifest,/android:allowBackup="false"/);
});

test('mobile commands are independent and never silently call remote AI or business tools',()=>{
 const brain=read('android/app/src/main/java/com/spark/companion/MobileBrain.kt');
 const activity=read('android/app/src/main/java/com/spark/companion/SparkMobileActivity.kt');
 assert.match(brain,/class MobileBrain/);
 assert.match(brain,/Offline local core active/);
 assert.match(brain,/not connected in this build/);
 assert.match(brain,/addNote\(note\)/);
 assert.match(brain,/addTask\(task\)/);
 assert.match(activity,/MobileBrain\(MobilePreferencesStore\(this\)\)/);
 assert.match(activity,/startActivity\(Intent\(this, MainActivity::class\.java\)\)/);
 assert.doesNotMatch(activity+brain,/https?:\/\/|purchaseOrder|executeShell|cloudApiKey|OpenAI|geminiClient/);
});

test('mobile voice input is user initiated and voice output requires installed offline engine',()=>{
 const activity=read('android/app/src/main/java/com/spark/companion/SparkMobileActivity.kt');
 assert.match(activity,/button\("VOICE IN"\) \{ beginSpeechRecognition\(\) \}/);
 assert.match(activity,/RecognizerIntent\.EXTRA_PREFER_OFFLINE, true/);
 assert.match(activity,/provider may use the network/);
 assert.match(activity,/!v\.isNetworkConnectionRequired/);
 assert.match(activity,/if \(speakReplies && localVoiceReady\)/);
 assert.match(activity,/tts\?\.shutdown\(\)/);
});

test('local notes are private and no Android sync or backup permission is added',()=>{
 const app=read('android/app/src/main/java/com/spark/companion/MobilePreferencesStore.kt');
 const manifest=read('android/app/src/main/AndroidManifest.xml');
 assert.match(app,/Context\.MODE_PRIVATE/);
 assert.match(app,/getSharedPreferences\("spark_mobile_local_v1"/);
 assert.match(app,/\.commit\(\)/);
 assert.doesNotMatch(app,/Firebase|Retrofit|WebSocket|OkHttp|http:\/\/|https:\/\//);
 assert.match(manifest,/android:usesCleartextTraffic="false"/);
});
