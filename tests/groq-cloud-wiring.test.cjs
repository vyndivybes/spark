const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');

test('Groq is explicit and does not alter known-good Gemini cinematic profile',()=>{
 const launcher=read('start-spark.ps1');
 const backend=read('backend/server.py');
 assert.match(launcher,/\[ValidateSet\('gemini', 'groq'\)\]/);
 assert.match(launcher,/\$AIProvider = 'gemini'/);
 assert.match(launcher,/\$env:SPARK_AI_PROVIDER = \$AIProvider/);
 assert.match(backend,/if cloud_provider\(\) == "groq":/);
 assert.match(backend,/async def start_groq_audio/);
 assert.match(backend,/GroqVoiceLoop\(/);
 assert.match(backend,/groq_configured/);
 assert.match(backend,/asyncio\.create_task\(audio_loop\.handle_text\(text\)\)/);
});

test('Groq voice uses the existing AEC microphone / speaker paths, not native PyAudio',()=>{
 const backend=read('backend/server.py');
 const groq=read('backend/spark_groq.py');
 const ui=read('src/App.jsx');
 assert.match(backend,/if AUDIO_TRANSPORT != "browser_aec":/);
 assert.match(backend,/audio_loop\.out_queue\.put_nowait/);
 assert.match(groq,/self\.on_browser_audio\(pcm\[start:start\+48000\]\)/);
 assert.match(groq,/async def process_pcm/);
 assert.match(ui,/Groq Hands-Free Cloud Ready/);
 assert.match(ui,/BrowserEchoAudio/);
});

test('No Ollama requirement, process launcher, hosted models require key privately',()=>{
 const manifest=read('requirements-runtime.txt');
 const groq=read('backend/spark_groq.py');
 assert.doesNotMatch(manifest,/^ollama/i);
 assert.doesNotMatch(groq,/localhost:11434|\bollama\.chat\b/i);
 assert.match(groq,/GROQ_API_KEY/);
 assert.match(groq,/api\.groq\.com/);
 assert.match(groq,/rate limit reached \(429\)/);
});
