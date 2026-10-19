const { app, BrowserWindow, ipcMain, shell, dialog, clipboard } = require('electron');
const fs = require('fs/promises');
const path = require('path');
const { spawn } = require('child_process');
const {trustedWorkspaceSender}=require('./workspace-auth.cjs');
const workspaceToken=require('node:crypto').randomBytes(32).toString('hex');
const {createExperienceManager}=require('./experience-manager.cjs');
const {BackendRecoveryBudget}=require('./backend-recovery.cjs');
const {collectLocalReaSummaries,formatReaInventory}=require('./rea-evidence.cjs');

// Use ANGLE D3D11 backend - more stable on Windows while keeping WebGL working
// This fixes "GPU state invalid after WaitForGetOffsetInRange" error
app.commandLine.appendSwitch('use-angle', 'd3d11');
app.commandLine.appendSwitch('enable-features', 'Vulkan');
app.commandLine.appendSwitch('ignore-gpu-blocklist');
 // SPARK is a user-controlled local desktop cockpit. Its automatic audible
 // greeting is intentionally allowed before the user clicks the window.
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');

let mainWindow;
let pythonProcess;
let quitting=false;
const backendRestartBudget=new BackendRecoveryBudget();
let experienceManager;
let lastReaInventory=null;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1920,
        height: 1080,
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
        const url = isDev ? 'http://localhost:5173' : null;
        const loadPromise = isDev
            ? mainWindow.loadURL(url)
            : mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));

        loadPromise
            .then(() => {
                console.log('Frontend loaded successfully!');
                windowWasShown = true;
                mainWindow.show();
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
    });
}

function startPythonBackend() {
    const scriptPath = path.join(__dirname, '../backend/server.py');
    console.log(`Starting Python backend: ${scriptPath}`);

    // Assuming 'python' is in PATH. In prod, this would be the executable.
    pythonProcess = spawn(process.env.SPARK_PYTHON || 'python', [scriptPath], {
        cwd: path.join(__dirname, '../backend'),
        env: {...process.env,SPARK_WORKSPACE_TOKEN:workspaceToken},
    });

    pythonProcess.on('error', (error) => {
        console.error('SPARK core backend could not launch. Experience Deck remains available:', error.message);
    });
    pythonProcess.stdout.on('data', (data) => {
        console.log(`[Python]: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`[Python Error]: ${data}`);
    });
    const child=pythonProcess;
    child.once('close', () => {
        if (quitting || child !== pythonProcess) return;
        const delay=backendRestartBudget.nextDelay();
        if(delay===null){
            console.error('SPARK backend restart limit reached. Manual repair required.');
            return;
        }
        console.warn('SPARK backend exited; attempting bounded recovery.');
        setTimeout(() => {
            if (!quitting && pythonProcess === child) startPythonBackend();
        }, delay);
    });
}

app.whenReady().then(() => {
    ipcMain.handle('spark:workspace-token',event=>{
        if(!trustedWorkspaceSender(event,mainWindow,path.join(__dirname,'../dist/index.html'),process.env.NODE_ENV!=='production'))
            throw new Error('Workspace access requires the root SPARK cockpit.');
        return workspaceToken;
    });
    experienceManager=createExperienceManager({
        root:path.resolve(__dirname,'..'),
        userData:app.getPath('userData'),
        python:process.env.SPARK_PYTHON||'python',
        notesDir:process.env.SPARK_NOTES_DIR || path.join(
            process.env.LOCALAPPDATA || path.join(require('node:os').homedir(),'.spark'),
            'SPARK','workspace','holo-notes'),
        BrowserWindow,
    });
    ipcMain.handle('spark:open-experience',async(event,name)=>{
        if(!mainWindow||event.sender.id!==mainWindow.webContents.id)
            throw new Error('Experience launch is only available from the SPARK cockpit.');
        return experienceManager.open(name);
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

    checkBackendPort(8000).then((isTaken) => {
        if (isTaken) {
            console.log('Port 8000 is taken. Assuming backend is already running manually.');
            waitForBackend().then(createWindow);
        } else {
            startPythonBackend();
            // Give it a moment to start, then wait for health check
            setTimeout(() => {
                waitForBackend().then(createWindow);
            }, 1000);
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
        const deadline=Date.now()+20000;
        let completed=false;
        const ready=(available)=>{if(!completed){completed=true;resolve(available);}};
        const retry=()=>{
            if(completed)return;
            if(Date.now()>=deadline){
                console.warn('SPARK core backend offline. Launching UI anyway; check Python dependencies.');
                ready(false);
                return;
            }
            setTimeout(check,1000);
        };
        const check=()=>{
            if(completed)return;
            const request=require('http').get('http://127.0.0.1:8000/status',res=>{
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

app.on('before-quit',()=>{quitting=true});

app.on('will-quit', () => {
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
