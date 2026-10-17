const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const read=name=>fs.readFileSync(path.join(root,name),'utf8');

test('closing SPARK normally does not return a false launcher failure',()=>{
 const pkg=JSON.parse(read('package.json'));
 assert.match(pkg.scripts.dev,/concurrently\s+-k\s+--success\s+first/);
});

test('backend uses its own Python environment and checks core imports first',()=>{
 const script=read('start-spark.ps1');
 assert.match(script,/\.venv[\\/]Scripts[\\/]python\.exe/);
 assert.match(script,/SPARK_PYTHON/);
 assert.match(script,/requirements-runtime\.txt/);
 assert.match(script,/runtime_preflight\.py/);
});

test('Python runtime manifest includes the modules imported by ADA backend',()=>{
 const manifest=read('requirements-runtime.txt');
 for(const requirement of ['python-socketio','uvicorn','fastapi','google-genai','opencv-python','pyaudio','pillow','mss','python-dotenv','python-kasa','mediapipe','aiohttp','zeroconf','playwright']){
  assert.match(manifest,new RegExp('^'+requirement+'(?:[=<>!~ ].*)?$', 'im'),requirement);
 }
});

test('no account key is required just to import the backend modules',()=>{
 const web=read('backend/web_agent.py');
 const ada=read('backend/ada.py');
 assert.doesNotMatch(web,/if not API_KEY:\s*raise ValueError/);
 assert.match(ada,/client\s*=\s*genai\.Client\([^\n]+\)\s+if\s+os\.getenv\(['\"]GEMINI_API_KEY/);
});

test('dead Python processes are not killed a second time and OS commands do not use shells',()=>{
 const main=read('electron/main.js');
 assert.match(main,/pythonProcess\.exitCode\s*===\s*null/);
 assert.match(main,/spawnSync\('taskkill'/);
 assert.doesNotMatch(main,/execSync\(\x60taskkill/);
});

test('SPARK opens its full cockpit without docking developer tools automatically',()=>{
 const main=read('electron/main.js');
 assert.match(main,/process\.env\.SPARK_DEVTOOLS\s*===\s*'1'/);
 assert.doesNotMatch(main,/if\s*\(isDev\)\s*\{\s*mainWindow\.webContents\.openDevTools\(\)/);
});

test('launcher accepts a selected allowlisted free-tier Gemini Live model',()=>{
 const script=read('start-spark.ps1');
 assert.match(script,/\[ValidateSet\('gemini-3\.8-live',\s*'gemini-3\.1-flash-live-preview'\)\]/);
 assert.match(script,/\[string\]\$LiveModel\s*=\s*'gemini-3\.8-live'/);
 assert.match(script,/\$env:SPARK_LIVE_MODEL\s*=\s*\$LiveModel/);
 assert.doesNotMatch(script,/\$env:SPARK_LIVE_MODEL\s*=\s*'gemini-3\.8-live'/);
});


test('explicit voice profile selects proven minimal Live config without discarding full mode',()=>{
 const launcher=read('start-spark.ps1');
 const ada=read('backend/ada.py');
 assert.match(launcher,/\[ValidateSet\('full',\s*'voice'\)\]/);
 assert.match(launcher,/\[string\]\$LiveProfile\s*=\s*'full'/);
 assert.match(launcher,/\$env:SPARK_LIVE_PROFILE\s*=\s*\$LiveProfile/);
 assert.match(ada,/select_live_config\(live_profile\(\),\s*config\)/);
});
