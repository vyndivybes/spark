// Isolated production renderer acceptance. No backend, provider or hardware access.
const {app, BrowserWindow, ipcMain, session} = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const assert = require('node:assert/strict');
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'spark-particles-'));
app.setPath('userData', directory);
app.disableHardwareAcceleration();
app.commandLine.appendSwitch('autoplay-policy','no-user-gesture-required');
const started = performance.now();
const errors = [];
const requests = [];
app.whenReady().then(async () => {
    let win;
    try {
        ipcMain.handle('spark:workspace-token', () => 'isolated-render-test');
        ipcMain.handle('spark:brain-display', () => require('../../electron/brain-display.cjs').readBrainDisplay(path.resolve(__dirname,'../..')));
        session.defaultSession.setPermissionRequestHandler((web, permission, callback) => callback(false));
        session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
            requests.push(details.url);
            callback({cancel: !details.url.startsWith('file:')});
        });
        win = new BrowserWindow({show:false, width:1440, height:960,
            webPreferences:{nodeIntegration:true, contextIsolation:false, backgroundThrottling:false}});
        win.webContents.on('console-message', (event, level, message) => {
            if (level === 3 && !/ERR_BLOCKED_BY_CLIENT|Failed to load resource/.test(message)) errors.push(message);
        });
        await win.loadFile(path.resolve(__dirname, '../../dist/index.html'));
        // The visualizer deliberately stops painting hidden documents.
        win.showInactive();
        const waitFor = async expression => {
            const end = Date.now()+15000;
            while (!await win.webContents.executeJavaScript(expression)) {
                if (Date.now()>end) throw Error('Renderer readiness timeout: '+expression);
                await new Promise(resolve => setTimeout(resolve,50));
            }
        };
        await waitFor("document.querySelector('.galaxy-provenance')?.textContent.includes('239 nodes')");
        const dashboardMs = performance.now()-started;
        await waitFor("!!document.querySelector('.voice-mode canvas.spatial-core-scene')?.width");
        await new Promise(resolve => setTimeout(resolve,250));
        const sample = () => win.webContents.executeJavaScript(`(() => {
            const c=document.querySelector('.voice-mode canvas.spatial-core-scene');
            const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
            let lit=0, hash=0, top=c.height, bottom=0;
            for(let i=3;i<d.length;i+=4){
                if(d[i]){lit++; const y=Math.floor((i-3)/4/c.width);top=Math.min(top,y);bottom=Math.max(bottom,y);}
                hash=(hash+d[i]*(i%997))%2147483647;
            }
            return {lit,hash,top,bottom,width:c.width,height:c.height};
        })()`);
        let first = await sample();
        const paintDeadline = Date.now()+5000;
        while (!first.lit && Date.now()<paintDeadline) {
            await new Promise(resolve=>setTimeout(resolve,50));
            first = await sample();
        }
        await new Promise(resolve => setTimeout(resolve,250));
        const second = await sample();
        console.log(JSON.stringify({first,second,dashboardMs:Math.round(dashboardMs)}));
        assert.ok(first.lit>5000, 'Particle network must paint visible pixels');
        assert.notEqual(first.hash,second.hash,'Network must animate over time');
        assert.ok(first.lit<first.width*first.height*.65,'Network must retain transparent gaps');
        assert.equal(await win.webContents.executeJavaScript("document.querySelector('.galaxy-wordmark').getAttribute('aria-label')"),'SPARK');
        const evidence = path.resolve(__dirname,'../../docs/evidence/brain-galaxy-cockpit.png');
        fs.writeFileSync(evidence,(await win.webContents.capturePage()).toPNG());
        await win.webContents.executeJavaScript("document.querySelector('button[aria-controls=\"spark-workspace-panel\"]').click()");
        await waitFor("!!document.querySelector('.cc-sidebar nav')");
        await win.webContents.executeJavaScript("[...document.querySelectorAll('.cc-sidebar nav button')].find(b=>b.textContent==='Knowledge').click()");
        await waitFor("!!document.querySelector('[aria-label=\"SPARK knowledge and skill workspace\"]')");
        // Check production resource boundaries, not a source-text approximation.
        assert.ok(!requests.some(url=>/vision_bundle|CadWindow|hand_landmarker|\/wasm/.test(url)),
            'Vision models and CAD must not load at startup');
        assert.deepEqual(errors,[],'No renderer exceptions');
        // Verify real Chromium FFTs using synthetic tones, without a microphone.
        const {readBrainDisplay}=require('../../electron/brain-display.cjs');
        const graph=await readBrainDisplay(path.resolve(__dirname,'../..'));
        const built=require('esbuild').buildSync({entryPoints:[path.join(__dirname,'galaxy-signal-preview.jsx')],
            bundle:true,write:false,format:'iife',platform:'browser',define:{'process.env.NODE_ENV':'"production"'}});
        const cssName=fs.readdirSync(path.resolve(__dirname,'../../dist/assets')).find(n=>n.endsWith('.css'));
        const css=fs.readFileSync(path.resolve(__dirname,'../../dist/assets',cssName),'utf8');
        const html='<html><head><style>'+css+'</style></head><body style="margin:0;background:#070c17"><div id="root"></div><script>window.galaxyFixtureGraph='+JSON.stringify(graph).replace(/</g,'\\u003c')+';</script><script>'+built.outputFiles[0].text.replace(/<\/script/g,'<\\/script')+'</script></body></html>';
        const signalFile=path.join(directory,'signal.html');fs.writeFileSync(signalFile,html);
        await win.loadFile(signalFile);
        await waitFor('!!window.galaxyTest');
        const frequencies=[187.5,937.5,3000,7500], spectrumResults=[];
        for(let band=0;band<4;band++){
            await win.webContents.executeJavaScript(`window.galaxyTest.tone(${frequencies[band]})`);
            await waitFor(`window.galaxyTest.bands()[${band}]>.08`);
            const bands=await win.webContents.executeJavaScript('window.galaxyTest.bands()');
            assert.equal(bands.indexOf(Math.max(...bands)),band,'Measured tone must activate its frequency colour');
            spectrumResults.push(bands);
        }
        await win.webContents.executeJavaScript('window.galaxyTest.chord()');
        await new Promise(resolve=>setTimeout(resolve,650));
        await win.webContents.executeJavaScript("document.querySelector('canvas').dispatchEvent(new PointerEvent('pointermove',{clientX:innerWidth*.7,clientY:innerHeight*.3}))");
        await new Promise(resolve=>setTimeout(resolve,200));
        const parallax=await win.webContents.executeJavaScript("parseFloat(document.querySelector('.brain-galaxy').style.getPropertyValue('--galaxy-look-y'))");
        assert.ok(parallax>0,'Pointer movement must change the 3D wordmark viewing angle');
        const pulseEvidence=path.resolve(__dirname,'../../docs/evidence/brain-galaxy-synthetic-frequencies.png');
        fs.writeFileSync(pulseEvidence,(await win.webContents.capturePage()).toPNG());
        await win.webContents.executeJavaScript('window.galaxyTest.mute()');
        assert.deepEqual(await win.webContents.executeJavaScript('window.galaxyTest.bands()'),[0,0,0,0]);
        await win.webContents.executeJavaScript('window.galaxyTest.stop()');
        assert.deepEqual(errors,[],'No exceptions during synthetic frequency acceptance');
        console.log(JSON.stringify({dashboardMs:Math.round(dashboardMs),network:first,
            secondFrameHash:second.hash, errors, deferredAssetsNotRequested:true, spectrumResults,
            muteClearsSpectrum:true,parallaxAngle:parallax,screenshot:evidence,syntheticToneScreenshot:pulseEvidence}));
        app.exit(0);
    } catch(error) { console.error(error.stack); app.exit(1); }
});
