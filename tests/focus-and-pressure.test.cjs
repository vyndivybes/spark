const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const moduleAt=p=>import(pathToFileURL(path.join(__dirname,'..',p)).href);
test('focus timer uses actual elapsed time, not interval callback count',async()=>{
 const {createFocusState,advanceFocus,remainingSeconds}=await moduleAt('src/utils/focusClock.mjs');
 let state=createFocusState(25);
 state=advanceFocus(state,{type:'start',minutes:25},100000);
 assert.equal(state.phase,'running');
 assert.equal(remainingSeconds(state,100000+5000),1495);
 state=advanceFocus(state,{type:'tick'},100000+25000);
 assert.equal(state.remainingSeconds,1475);
 state=advanceFocus(state,{type:'pause'},100000+26000);
 assert.equal(state.phase,'paused');
 assert.equal(remainingSeconds(state,100000+120000),1474);
 state=advanceFocus(state,{type:'resume'},100000+180000);
 assert.equal(remainingSeconds(state,100000+185000),1469);
 state=advanceFocus(state,{type:'tick'},100000+180000+1475*1000);
 assert.equal(state.phase,'completed');
 assert.equal(remainingSeconds(state,99999999),0);
});
test('focus timer rejects invalid durations and never claims attention tracking',async()=>{
 const {createFocusState,advanceFocus}=await moduleAt('src/utils/focusClock.mjs');
 for(const v of [-1,0,0.5,241,Infinity,NaN,'25']){
   assert.throws(()=>createFocusState(v));
 }
 const idle=createFocusState(5);
 assert.equal(idle.observationMode,'timer_only');
 assert.equal(idle.onTargetPercent,null);
 assert.equal(advanceFocus(idle,{type:'pause'},0).phase,'idle');
 assert.equal(advanceFocus(idle,{type:'reset'},0).remainingSeconds,5*60);
});
test('resource advice is derived from valid readings without false device diagnosis',async()=>{
 const {getPressureAdvice}=await moduleAt('src/utils/systemPressure.mjs');
 const report=getPressureAdvice({ram_percent:80.7,disk_free_gb:13.89,battery_percent:24,ac_connected:false,cpu_percent:28.8});
 assert.equal(report.length,3);
 assert.deepEqual(report.map(x=>x.id),['memory','storage','battery']);
 assert.match(report[0].text,/Close unused/i);
 assert.match(report[1].text,/13.89 GB/);
 assert.match(report[2].text,/charger/i);
 assert.ok(report.every(x=>x.action==='advice_only'));
 assert.equal(getPressureAdvice({ram_percent:63,disk_free_gb:80,battery_percent:72,ac_connected:true}).length,0);
 assert.equal(getPressureAdvice({ram_percent:'80.7',disk_free_gb:-1,battery_percent:null,ac_connected:'false'}).length,0);
});
test('resource advice remains bounded for extreme values',async()=>{
 const {getPressureAdvice}=await moduleAt('src/utils/systemPressure.mjs');
 const a=getPressureAdvice({ram_percent:100,disk_free_gb:0,battery_percent:0,ac_connected:false,cpu_percent:100});
 assert.equal(a.length,4);
 assert.equal(getPressureAdvice({ram_percent:999,disk_free_gb:1e50,battery_percent:-9,ac_connected:false}).length,0);
});
test('focus panel retains timer state when hidden; UI never claims app tracking',()=>{
 const app=fs.readFileSync(path.join(__dirname,'../src/App.jsx'),'utf8');
 const focus=fs.readFileSync(path.join(__dirname,'../src/components/FocusPanel.jsx'),'utf8');
 const sys=fs.readFileSync(path.join(__dirname,'../src/components/SystemCenter.jsx'),'utf8');
 assert.match(app,/FOCUS/);
 assert.match(app,/<FocusPanel/);
 assert.match(app,/visible=\{showFocus\}/);
 assert.match(focus,/state\.observationMode/);
 assert.match(focus,/setInterval/);
 assert.match(focus,/advanceFocus/);
 assert.match(focus,/This timer does not monitor/i);
 assert.match(sys,/getPressureAdvice/);
 assert.match(sys,/Resource advisories/);
 assert.doesNotMatch(focus,/getDisplayMedia|getUserMedia|localStorage|fetch\(/);
});
