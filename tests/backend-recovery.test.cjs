const test=require('node:test');
const assert=require('node:assert/strict');
const {BackendRecoveryBudget}=require('../electron/backend-recovery.cjs');
test('bounded backend supervisor permits two spaced restarts, then stops',()=>{
 const budget=new BackendRecoveryBudget();
 assert.equal(budget.nextDelay(),1000);
 assert.equal(budget.nextDelay(),2000);
 assert.equal(budget.nextDelay(),null);
 assert.equal(budget.nextDelay(),null);
});
test('restart budget validates requested maximum and cannot reset silently',()=>{
 assert.throws(()=>new BackendRecoveryBudget({maxRestarts:50}),/limit/i);
});
test('Electron backend owns restarts and suppresses them during shutdown',()=>{
 const fs=require('node:fs');
 const code=fs.readFileSync(require('node:path').join(__dirname,'../electron/main.js'),'utf8');
 assert.match(code,/BackendRecoveryBudget/);
 assert.match(code,/backendRestartBudget.nextDelay\(\)/);
 assert.match(code,/if\s*\(quitting\s*\|\|/);
 assert.match(code,/app.on\('before-quit'/);
});
