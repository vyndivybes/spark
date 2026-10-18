const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const p=file=>fs.readFileSync(path.resolve(__dirname,'..',file),'utf8');
test('system status adds noninvasive vitals without host paths or new dependencies',()=>{
 const server=p('backend/server.py');
 const panel=p('src/components/SystemCenter.jsx');
 const pure=p('backend/spark_host_vitals.py');
 const deps=p('requirements-runtime.txt');
 assert.match(server,/asyncio\.to_thread\(collect_host_vitals\)/);
 assert.match(server,/safe_diagnostics\(status_data,/);
 assert.match(panel,/Windows hardware \/ read-only/);
 assert.match(panel,/RAM usage/);
 assert.match(panel,/Disk available/);
 assert.match(panel,/Battery/);
 assert.match(pure,/GetSystemTimes/);
 assert.match(pure,/GlobalMemoryStatusEx/);
 assert.match(pure,/GetSystemPowerStatus/);
 assert.doesNotMatch(pure,/subprocess|kill_process|terminate\(|api_key|HTTP/);
 assert.doesNotMatch(deps,/screen_brightness_control/);
});
test('safe clipboard report includes only normalized numbers from host vitals',async()=>{
 const {formatHealthReport}=await import(pathToFileURL(path.resolve(__dirname,'../src/utils/sessionTools.mjs')).href);
 const report=formatHealthReport({ai_provider:'groq',host:{
 cpu_percent:44.8,ram_percent:70.1,disk_free_gb:12.34,
 battery_percent:82.5,ac_connected:true,
 drive_path:'C:\\Users\\ASUS\\Private',
 token:'SECRET'
 }});
 assert.match(report,/CPU: 44.8%/);
 assert.match(report,/RAM usage: 70.1%/);
 assert.match(report,/Disk available: 12.34 GB/);
 assert.match(report,/Battery: 82.5%/);
 assert.doesNotMatch(report,/ASUS|Private|SECRET|C:\\/);
});
