const { app, BrowserWindow, ipcMain, shell, dialog, clipboard, session } = require('electron');
const fs = require('fs/promises');
const path = require('path');
const { spawn } = require('child_process');
const {trustedWorkspaceSender}=require('./workspace-auth.cjs');
// Honor a deterministic launcher-provided token (parallel installs and
// vesting harnesses); otherwise generate a fresh per-launch token.
const workspaceToken=(process.env.SPARK_WORKSPACE_TOKEN
      && process.env.SPARK_WORKSPACE_TOKEN.length===64
      && /^[0-9a-f]+$/.test(process.env.SPARK_WORKSPACE_TOKEN))
    ? process.env.SPARK_WORKSPACE_TOKEN
    : require('node:crypto').randomBytes(32).toString('hex');
const {createExperienceManager}=require('./experience-manager.cjs');
const {classifyBackendWait}=require('./backend-health.cjs');
const {createWhatsAppWindow}=require('./whatsapp-window.cjs');
const {createJarvisBridge}=require('./jarvis-bridge.cjs');
const {createBusinessPortals}=require('./business-portals.cjs');
const {collectLocalReaSummaries,formatReaInventory}=require('./rea-evidence.cjs');
const {readBrainDisplay}=require('./brain-display.cjs');
const {createReaPreview}=require('./rea-preview.cjs');

// A desktop click reuses the current application instead of starting another
// frontend/backend pair and competing for Chromium's cache and loopback ports.
if (!app.requestSingleInstanceLock()) {
    app.quit();
} else {

// Use ANGLE D3D11 backend - more stable on Windows while keeping WebGL working
// This fixes "GPU state invalid after WaitForGetOffsetInRange" error
app.commandLine.appendSwitch('use-angle', 'd3d11');
app.commandLine.appendSwitch('enable-features', 'Vulkan');
app.commandLine.appendSwitch('ignore-gpu-blocklist');
 // SPARK is a user-controlled local desktop cockpit. Its automatic audible
 // greeting is intentionally allowed before the user clicks the window.
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');

let mainWindow;
app.on('second-instance', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.show();
        mainWindow.focus();
    } else {
        createWindow();
    }
});
let pythonProcess;
let backendExitNotice=null;
let appQuitting=false;
let experienceManager;
let whatsappWindow;
let jarvisBridge,jarvisBridgeUrl;
let businessPortals;
let lastReaInventory=null;

// Packaged builds place backend/public/vendor under process.resourcesPath via
// electron-builder extraResources; in dev they sit next to the repo root.
function resolveResource(...segments){
    const base = app.isPackaged ? process.resourcesPath : path.join(__dirname, '..');
    return path.join(base, ...segments);
}

// Prefer the bundled relocatable Python runtime (python-runtime/) so packaged
// users need no system Python. Fall back to SPARK_PYTHON, then PATH python.
function resolvePython(){
    if(process.env.SPARK_PYTHON) return process.env.SPARK_PYTHON;
    const bundled = resolveResource('python-runtime', 'python.exe');
    try { if(require('fs').existsSync(bundled)) return bundled; } catch(_) {}
    return 'python';
}

function resolveWindowIcon() {
    const icon = resolveResource('public', 'spark.ico');
    try { return require('fs').existsSync(icon) ? icon : undefined; }
    catch (_) { return undefined; }
}

function createWindow() {
    const windowIcon = resolveWindowIcon();
    mainWindow = new BrowserWindow({
        width: 1920,
        height: 1080,
        ...(windowIcon ? { icon: windowIcon } : {}),
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false, // For simple IPC/Socket.IO usage
            autoplayPolicy: 'no-user-gesture-required',
        },
        backgroundColor: '#0b1220',
        frame: false, // Frameless SPARK cockpit with custom chrome
        titleBarStyle: 'hidden',
        show: false, // Don't show until ready
    });

    // In dev, load Vite server. In prod, load index.html
    const isDev = process.env.NODE_ENV !== 'production';

    const loadFrontend = (retries = 3) => {
        const backendPort = process.env.SPARK_BACKEND_PORT || '8000';
        const url = isDev ? 'http://localhost:5173' : null;
        const loadPromise = isDev
            ? mainWindow.loadURL(url)
            : mainWindow.loadFile(path.join(__dirname, '../dist/index.html'), {query: {sparkBackendPort: backendPort}});

        loadPromise
            .then(() => {
                console.log('Frontend loaded successfully!');
                windowWasShown = true;
                mainWindow.show();
                if(process.env.SPARK_OPEN_JARVIS==='1')jarvisBridge.open().catch(()=>console.warn('VAOS sign-in window could not open. Use the Jarvis panel to retry.'));
                if(process.env.SPARK_OPEN_WHATSAPP==='1')whatsappWindow.open().catch(()=>console.warn('WhatsApp could not open. Use the experience library to retry.'));
                // Developer tools intentionally remain opt-in. Auto-docking them
                // covered half the SPARK cockpit and triggered cramped card layout.
                if (isDev && process.env.SPARK_DEVTOOLS === '1') {
                    mainWindow.webContents.openDevTools();
                }
            })
            .catch((err) => {
                console.error(`Failed to load frontend: ${err.message}`);
                if (retries > 0) {
                    console.log(`Retrying in 1 second... (${retries} retries left)`);
                    setTimeout(() => loadFrontend(retries - 1), 1000);
                } else {
                    console.error('Failed to load frontend after all retries. Keeping window open.');
                    windowWasShown = true;
                    mainWindow.show(); // Show anyway so user sees something
                }
            });
    };

    loadFrontend();

    mainWindow.on('closed', () => {
        mainWindow = null;
        // Hidden account/experience windows must not keep the Windows cockpit
        // instance locked after its owner closes the main window.
        if (process.platform !== 'darwin') app.quit();
    });
}

function startPythonBackend() {
    const backendDir = resolveResource('backend');
    const scriptPath = path.join(backendDir, 'server.py');
    console.log(`Starting Python backend: ${scriptPath}`);

    // Assuming 'python' is in PATH. In prod, this would be the executable.
    backendExitNotice=null;
    pythonProcess = spawn(resolvePython(), [scriptPath], {
        cwd: backendDir,
        env: {...process.env,SPARK_WORKSPACE_TOKEN:workspaceToken,SPARK_JARVIS_BRIDGE_URL:jarvisBridgeUrl},
    });

    pythonProcess.on('error', (error) => {
        backendExitNotice={code:null,signal:null,error:error.message};
        console.error('SPARK core backend could not launch. Experience Deck remains available:', error.message);
    });
    pythonProcess.on('exit', (code, signal) => {
        backendExitNotice={code,signal};
        if(!appQuitting){
            console.warn(`SPARK core backend exited (code=${code ?? 'none'}, signal=${signal ?? 'none'}). The cockpit remains available; check Python dependencies.`);
        }
    });
    pythonProcess.stdout.on('data', (data) => {
        console.log(`[Python]: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`[Python Error]: ${data}`);
    });
}

app.whenReady().then(async () => {
    whatsappWindow=createWhatsAppWindow({BrowserWindow});
    businessPortals=createBusinessPortals({BrowserWindow,session});
    jarvisBridge=createJarvisBridge({BrowserWindow,session,token:workspaceToken,origin:process.env.SPARK_VAOS_URL,
        businessRead:id=>businessPortals.read(id),whatsappStatus:()=>whatsappWindow.status(),
        whatsappRead:args=>whatsappWindow.readChats(args)});
    jarvisBridgeUrl=await jarvisBridge.listen();
    ipcMain.handle('spark:jarvis',async(event,request)=>{
        if(!trustedWorkspaceSender(event,mainWindow,path.join(__dirname,'../dist/index.html'),process.env.NODE_ENV!=='production'))
            throw Error('Jarvis access requires the root SPARK cockpit.');
        switch(request?.action){
            case 'open-portal':return businessPortals.open(request.portal);
            case 'read-portal':return businessPortals.read(request.portal);
            case 'open':return jarvisBridge.open();
            case 'status':return jarvisBridge.status();
            case 'ask':return jarvisBridge.ask(request.question);
            case 'disconnect':return jarvisBridge.disconnect();
            default:throw Error('Unknown Jarvis operation.');
        }
    });
    ipcMain.handle('spark:workspace-token',event=>{
        if(!trustedWorkspaceSender(event,mainWindow,path.join(__dirname,'../dist/index.html'),process.env.NODE_ENV!=='production'))
            throw new Error('Workspace access requires the root SPARK cockpit.');
        return workspaceToken;
    });
    const dataRoot = process.env.SPARK_WORKSPACE_DATA_ROOT || path.join(
        process.env.LOCALAPPDATA || path.join(require('node:os').homedir(),'.spark'),
        'SPARK','workspace');
    const reaPreview=createReaPreview({BrowserWindow,session,root:dataRoot,recipeFile:resolveResource('backend','spark_rea_notes.html'),blueprintFile:resolveResource('backend','spark_rea_app.html')});
    ipcMain.handle('spark:rea-preview',async(event,request)=>{
        if(!trustedWorkspaceSender(event,mainWindow,path.join(__dirname,'../dist/index.html'),process.env.NODE_ENV!=='production'))
            throw Error('App previews require the owning SPARK cockpit.');
        if(!request||!['test','open'].includes(request.action)||Object.keys(request).sort().join(',')!=='action,id,project')
            throw Error('Invalid preview request.');
        return reaPreview[request.action](request.project,request.id);
    });
    ipcMain.handle('spark:brain-display', async event => {
        if(!trustedWorkspaceSender(event,mainWindow,path.join(__dirname,'../dist/index.html'),process.env.NODE_ENV!=='production'))
            throw Error('Brain display requires the SPARK cockpit.');
        return readBrainDisplay(app.isPackaged ? process.resourcesPath : path.resolve(__dirname,'..'));
    });
    experienceManager=createExperienceManager({
        root:path.resolve(__dirname,'..'),
        userData:app.getPath('userData'),
        vayuExportsDir:path.join(dataRoot,'vayu-exports'),
        python:process.env.SPARK_PYTHON||'python',
        notesDir:process.env.SPARK_NOTES_DIR || path.join(dataRoot,'holo-notes'),
        BrowserWindow,
    });
    ipcMain.handle('spark:open-experience',async(event,name)=>{
        if(!mainWindow||event.sender.id!==mainWindow.webContents.id)
            throw new Error('Experience launch is only available from the SPARK cockpit.');
        return name==='whatsapp' ? whatsappWindow.open() : experienceManager.open(name);
    });
    ipcMain.handle('spark:open-grounding-source', async (event, url) => {
        // Never load third-party webpages into the privileged SPARK
        // Electron renderer. Open only HTTPS sources in user's browser.
        if (!mainWindow || event.sender.id !== mainWindow.webContents.id ||
            typeof url !== 'string' || url.length > 2048) {
            throw new Error('Grounding source not allowed.');
        }
        let parsed;
        try { parsed = new URL(url); }
        catch { throw new Error('Invalid source URL.'); }
        if (parsed.protocol !== 'https:' || !parsed.hostname ||
            parsed.username || parsed.password) {
            throw new Error('Only HTTPS grounded sources may open.');
        }
        return shell.openExternal(parsed.href);
    });
    ipcMain.handle('spark:copy-diagnostics', async (event, report) => {
        // Accept only a generated, whitelisted systems report, never raw
        // device secrets, chat, local files or unbounded provider output.
        if (!mainWindow || event.sender.id !== mainWindow.webContents.id ||
            typeof report !== 'string' || report.length > 4000 ||
            !report.startsWith('SPARK systems report — no keys or conversation content')) {
            throw new Error('Invalid diagnostic report');
        }
        clipboard.writeText(report);
        return {copied:true};
    });

    ipcMain.handle('spark:save-transcript', async (event, content) => {
        if (!mainWindow || event.sender.id !== mainWindow.webContents.id ||
            typeof content !== 'string' || content.length > 210000 ||
            !content.startsWith('# SPARK session transcript')) {
            throw new Error('Invalid transcript export');
        }
        const day = new Date().toISOString().slice(0,10);
        const result = await dialog.showSaveDialog(mainWindow, {
            title: 'Save SPARK conversation — may contain private data',
            defaultPath: 'SPARK-Session-'+day+'.md',
            filters: [{name:'Markdown',extensions:['md']}],
            properties:['showOverwriteConfirmation','createDirectory'],
        });
        if (result.canceled || !result.filePath) return {saved:false};
        await fs.writeFile(result.filePath, content, {encoding:'utf8'});
        return {saved:true};  // Do not leak the selected local path to renderer.
    });

    ipcMain.handle('spark:scan-rea-reports', async(event) => {
        if(!mainWindow || event.sender.id !== mainWindow.webContents.id)
            throw Error('Only the SPARK cockpit may request REA audit.');
        // Explicit UI-initiated, local-only read. No request-controlled paths.
        const result=await collectLocalReaSummaries({home:app.getPath('home')});
        lastReaInventory=result;
        return result;
    });
    ipcMain.handle('spark:copy-rea-inventory', async(event) => {
        if(!mainWindow || event.sender.id !== mainWindow.webContents.id ||
           !lastReaInventory || !lastReaInventory.report_count)
            throw Error('No approved REA inventory available.');
        clipboard.writeText(formatReaInventory(lastReaInventory));
        return {copied:true};
    });

    ipcMain.on('window-minimize', () => {
        if (mainWindow) mainWindow.minimize();
    });

    ipcMain.on('window-maximize', () => {
        if (mainWindow) {
            if (mainWindow.isMaximized()) {
                mainWindow.unmaximize();
            } else {
                mainWindow.maximize();
            }
        }
    });

    ipcMain.on('window-close', () => {
        if (mainWindow) mainWindow.close();
    });

    const backendPortNumber = Number(process.env.SPARK_BACKEND_PORT) || 8000;
    // Paint the cockpit while Python imports and initializes. Socket.IO reconnects
    // when the core becomes available; backend readiness must not hide the UI.
    createWindow();
    checkBackendPort(backendPortNumber).then((isTaken) => {
        if (isTaken) {
            console.log('Port '+backendPortNumber+' is taken. Assuming backend is already running manually.');
            waitForBackend();
        } else {
            startPythonBackend();
            waitForBackend();
        }
    });

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

function checkBackendPort(port) {
    return new Promise((resolve) => {
        const net = require('net');
        const server = net.createServer();
        server.once('error', (err) => {
            if (err.code === 'EADDRINUSE') {
                resolve(true);
            } else {
                resolve(false);
            }
        });
        server.once('listening', () => {
            server.close();
            resolve(false);
        });
        server.listen(port);
    });
}

function waitForBackend() {
    return new Promise((resolve) => {
        const started=Date.now();
        let completed=false;
        let startingNoticeShown=false;
        const ready=(available)=>{if(!completed){completed=true;resolve(available);}};
        const retry=()=>{
            if(completed)return;
            // A child that exited is a real failure, not a slow import. The exit
            // handler already logged the reason; stop probing and let the UI stay up.
            if(backendExitNotice){
                ready(false);
                return;
            }
            const childAlive=Boolean(pythonProcess && pythonProcess.pid
                && pythonProcess.exitCode===null && pythonProcess.signalCode===null);
            const state=classifyBackendWait({childAlive,elapsedMs:Date.now()-started});
            if(state.state==='offline'){
                console.warn(state.message);
                ready(false);
                return;
            }
            if(state.state==='starting'){
                if(!startingNoticeShown){
                    console.log(state.message);
                    startingNoticeShown=true;
                }
                setTimeout(check,2000);
                return;
            }
            setTimeout(check,1000);
        };
        const check=()=>{
            if(completed)return;
            const backendPort=process.env.SPARK_BACKEND_PORT||'8000';
            const request=require('http').get(`http://127.0.0.1:${backendPort}/status`,res=>{
                res.resume();
                if(res.statusCode===200)ready(true);
                else retry();
            });
            request.setTimeout(1500,()=>request.destroy());
            request.on('error',retry);
        };
        check();
    });
}

let windowWasShown = false;

app.on('window-all-closed', () => {
    // Only quit if the window was actually shown at least once
    // This prevents quitting during startup if window creation fails
    if (process.platform !== 'darwin' && windowWasShown) {
        app.quit();
    } else if (!windowWasShown) {
        console.log('Window was never shown - keeping app alive to allow retries');
    }
});

app.on('will-quit', () => {
    appQuitting=true;
    whatsappWindow?.close();
    jarvisBridge?.close();
    businessPortals?.close();
    experienceManager?.stopAll();
    console.log('App closing... Killing Python backend.');
    if (pythonProcess) {
        // A missing-Python or crashed backend has already exited. Do not send
        // taskkill to a stale PID or produce a misleading shutdown error.
        if (pythonProcess.pid && pythonProcess.exitCode === null && pythonProcess.signalCode === null) {
            if (process.platform === 'win32') {
                const { spawnSync } = require('child_process');
                const stopped = spawnSync('taskkill',
                    ['/PID', String(pythonProcess.pid), '/T', '/F'],
                    { windowsHide: true, stdio: 'ignore', timeout: 3000 });
                if (stopped.error) console.warn('Could not stop SPARK Python backend:', stopped.error.message);
            } else {
                pythonProcess.kill('SIGTERM');
            }
        }
        pythonProcess = null;
    }
});
}
