import sys
import asyncio

# Fix for asyncio subprocess support on Windows
# MUST BE SET BEFORE OTHER IMPORTS
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import socketio
import uvicorn
from fastapi import FastAPI
import asyncio
import threading
import sys
import os
import json
from datetime import datetime
from pathlib import Path



# Ensure we can import ada
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import ada
from spark_live_config import live_status, live_status_report
from spark_live_profile import live_profile
from spark_audio_meter import AudioMeter
from spark_browser_audio import select_transport, validate_pcm
from spark_groq import GroqVoiceLoop, GroqUnavailable, cloud_provider, groq_model
from authenticator import FaceAuthenticator
from kasa_agent import KasaAgent

# Create a Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI()
app_socketio = socketio.ASGIApp(sio, app)

import signal

# --- SHUTDOWN HANDLER ---
def signal_handler(sig, frame):
    print(f"\n[SERVER] Caught signal {sig}. Exiting gracefully...")
    # Clean up audio loop
    if audio_loop:
        try:
            print("[SERVER] Stopping Audio Loop...")
            audio_loop.stop() 
        except:
            pass
    # Force kill
    print("[SERVER] Force exiting...")
    os._exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Global state
audio_loop = None
loop_task = None
live_state = "idle"
live_message = ""
authenticator = None
kasa_agent = KasaAgent()
AUDIO_TRANSPORT = select_transport(os.environ.get("SPARK_AUDIO_TRANSPORT"))
SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "face_auth_enabled": False, # Default OFF as requested
    "tool_permissions": {
        "generate_cad": True,
        "run_web_agent": True,
        "write_file": True,
        "read_directory": True,
        "read_file": True,
        "create_project": True,
        "switch_project": True,
        "list_projects": True
    },
    "printers": [], # List of {host, port, name, type}
    "kasa_devices": [], # List of {ip, alias, model}
    "camera_flipped": False # Invert cursor horizontal direction
}

SETTINGS = DEFAULT_SETTINGS.copy()

def load_settings():
    global SETTINGS
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                loaded = json.load(f)
                # Merge with defaults to ensure new keys exist
                # Deep merge for tool_permissions would be better but shallow merge of top keys + tool_permissions check is okay for now
                for k, v in loaded.items():
                    if k == "tool_permissions" and isinstance(v, dict):
                         SETTINGS["tool_permissions"].update(v)
                    else:
                        SETTINGS[k] = v
            print(f"Loaded settings: {SETTINGS}")
        except Exception as e:
            print(f"Error loading settings: {e}")

def save_settings():
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(SETTINGS, f, indent=4)
        print("Settings saved.")
    except Exception as e:
        print(f"Error saving settings: {e}")

# Load on startup
load_settings()

authenticator = None
kasa_agent = KasaAgent(known_devices=SETTINGS.get("kasa_devices"))
# tool_permissions is now SETTINGS["tool_permissions"]

@app.on_event("startup")
async def startup_event():
    import sys
    print(f"[SERVER DEBUG] Startup Event Triggered")
    print(f"[SERVER DEBUG] Python Version: {sys.version}")
    try:
        loop = asyncio.get_running_loop()
        print(f"[SERVER DEBUG] Running Loop: {type(loop)}")
        policy = asyncio.get_event_loop_policy()
        print(f"[SERVER DEBUG] Current Policy: {type(policy)}")
    except Exception as e:
        print(f"[SERVER DEBUG] Error checking loop: {e}")

    print("[SERVER] Startup: Initializing Kasa Agent...")
    await kasa_agent.initialize()

@app.get("/status")
async def status():
    return {"status": "running", "service": "SPARK Core",
            "gemini_configured": ada.client is not None,
            "groq_configured": bool(os.environ.get("GROQ_API_KEY")),
            "ai_provider": cloud_provider(),
            "live_model": groq_model() if cloud_provider() == "groq" else ada.MODEL,
            "live_profile": "groq_voice" if cloud_provider() == "groq" else live_profile(),
            "audio_transport": AUDIO_TRANSPORT,
            "hands_free_ready": bool(audio_loop and getattr(audio_loop, "browser_ready", False)),
            **live_status_report(live_state, live_message)}

@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")
    await sio.emit('audio_transport_config', {'mode': AUDIO_TRANSPORT, 'provider': cloud_provider()}, room=sid)
    await sio.emit('status', {'msg': 'Connected to SPARK Core backend'}, room=sid)
    if cloud_provider() == "groq":
        await sio.emit('ai_status', {
            'state': 'idle', 'model': groq_model(),
            'message': 'Groq is selected. Start hands-free voice to connect.'}, room=sid)
    else:
        await sio.emit('ai_status', live_status(ada.client is not None, ada.MODEL), room=sid)

    global authenticator
    
    # Callback for Auth Status
    async def on_auth_status(is_auth):
        print(f"[SERVER] Auth status change: {is_auth}")
        await sio.emit('auth_status', {'authenticated': is_auth})

    # Callback for Auth Camera Frames
    async def on_auth_frame(frame_b64):
        await sio.emit('auth_frame', {'image': frame_b64})

    # Initialize Authenticator if not already done
    if authenticator is None:
        authenticator = FaceAuthenticator(
            reference_image_path="reference.jpg",
            on_status_change=on_auth_status,
            on_frame=on_auth_frame
        )
    
    # Check if already authenticated or needs to start
    if authenticator.authenticated:
        await sio.emit('auth_status', {'authenticated': True})
    else:
        # Check Settings for Auth
        if SETTINGS.get("face_auth_enabled", False):
            await sio.emit('auth_status', {'authenticated': False})
            # Start the auth loop in background
            asyncio.create_task(authenticator.start_authentication_loop())
        else:
            # Bypass Auth
            print("Face Auth Disabled. Auto-authenticating.")
            # We don't change authenticator state to true to avoid confusion if re-enabled? 
            # Or we should just tell client it's auth'd.
            await sio.emit('auth_status', {'authenticated': True})

@sio.event
async def get_audio_transport(sid):
    await sio.emit('audio_transport_config', {'mode': AUDIO_TRANSPORT, 'provider': cloud_provider()}, room=sid)


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")
    # AEC playback reference disappears when the Electron owner disconnects.
    # Stop the session rather than switch behind the user's back to a live mic.
    if audio_loop and audio_loop.browser_audio and audio_loop.owner_sid == sid:
        audio_loop.set_paused(True)
        audio_loop.stop()
        if loop_task and not loop_task.done():
            loop_task.cancel()

async def start_groq_audio(sid, data=None):
    """Optional Groq cloud voice, bypassing Gemini Live and ALL local models."""
    global audio_loop, loop_task, live_state, live_message

    if AUDIO_TRANSPORT != "browser_aec":
        await sio.emit('error', {'msg': 'Groq hands-free mode requires browser_aec audio.'}, room=sid)
        return
    if audio_loop and loop_task and not loop_task.done():
        await sio.emit('status', {'msg': 'Groq hands-free session already running.'}, room=sid)
        return
    if not os.environ.get("GROQ_API_KEY"):
        live_state = "setup_required"
        live_message = "Set GROQ_API_KEY in the private backend/.env file."
        await sio.emit('ai_status', {'state': 'setup_required','model': groq_model(),
          'message': 'Groq API key missing. Add GROQ_API_KEY to backend/.env.'}, room=sid)
        return
    # No arbitrary desktop action is authorized by this free-cloud fallback.
    # The fixed-route public APIs provide read-only factual retrieval.
    def on_transcription(payload):
        asyncio.create_task(sio.emit('transcription', payload, room=sid))
    def on_browser_audio(pcm):
        asyncio.create_task(sio.emit('browser_audio', pcm, room=sid))
    def on_web_sources(payload):
        asyncio.create_task(sio.emit('web_sources', payload, room=sid))
    def on_error(message):
        asyncio.create_task(sio.emit('error', {'msg': str(message)[:180]}, room=sid))
    def on_live_status(payload):
        global live_state, live_message
        live_state = payload.get('state', 'error')
        live_message = payload.get('message', '')
        asyncio.create_task(sio.emit('ai_status', payload, room=sid))
    try:
        audio_loop=GroqVoiceLoop(
            on_transcription=on_transcription,
            on_browser_audio=on_browser_audio,
            on_web_sources=on_web_sources,
            on_error=on_error,
            on_live_status=on_live_status,
        )
        audio_loop.owner_sid=sid
        audio_loop.set_paused(True)
        live_state='connecting'
        live_message='Starting Groq cloud hands-free speech.'
        loop_task=asyncio.create_task(audio_loop.run())
        def on_exit(task):
            global audio_loop, loop_task, live_state
            if task is loop_task:
                loop_task=None
                audio_loop=None
                live_state='idle'
        loop_task.add_done_callback(on_exit)
    except GroqUnavailable as exc:
        live_state='setup_required'
        await sio.emit('ai_status', {
            'state':'setup_required','model':groq_model(),
            'message':str(exc)}, room=sid)
    except Exception:
        live_state='error'
        await sio.emit('ai_status', {
            'state':'error','model':groq_model(),
            'message':'Groq voice engine failed to initialize.'}, room=sid)


@sio.event
async def start_audio(sid, data=None):
    global audio_loop, loop_task, live_state, live_message
    
    # Optional: Block if not authenticated
    # Only block if auth is ENABLED and not authenticated
    if SETTINGS.get("face_auth_enabled", False):
        if authenticator and not authenticator.authenticated:
            print("Blocked start_audio: Not authenticated.")
            await sio.emit('error', {'msg': 'Authentication Required'})
            return

    if cloud_provider() == "groq":
        await start_groq_audio(sid, data)
        return

    if ada.client is None:
        live_state = "setup_required"
        live_message = "Configure the SPARK Gemini key."
        await sio.emit('ai_status', live_status(False, ada.MODEL), room=sid)
        return

    request_transport = data.get("transport") if isinstance(data, dict) else None
    if request_transport and request_transport != AUDIO_TRANSPORT:
        await sio.emit('error', {'msg': 'Audio transport mismatch; restart SPARK with the selected launcher mode.'}, room=sid)
        return
    print("Starting SPARK Live Audio Loop...")
    
    device_index = None
    device_name = None
    if data:
        if 'device_index' in data:
            device_index = data['device_index']
        if 'device_name' in data:
            device_name = data['device_name']
            
    print(f"Using input device: Name='{device_name}', Index={device_index}")
    
    if audio_loop:
        if loop_task and (loop_task.done() or loop_task.cancelled()):
             print("Audio loop task appeared finished/cancelled. Clearing and restarting...")
             audio_loop = None
             loop_task = None
        else:
             print("Audio loop already running. Re-connecting client to session.")
             await sio.emit('status', {'msg': 'A.D.A Already Running'})
             return


    # Emit a compact visualization level at most ten times a second.
    # Never serialize the full PCM chunk into thousands of JSON integers.
    audio_meter = AudioMeter()
    def on_audio_data(data_bytes):
        level = audio_meter.sample(data_bytes)
        if level is not None:
            asyncio.create_task(sio.emit('audio_level', {'value': level}))

    def on_browser_audio(data_bytes):
        # Socket.IO emits raw binary; never JSON-serialize speaker PCM.
        asyncio.create_task(sio.emit('browser_audio', data_bytes, room=sid))

    # Google Search attribution is source metadata, never generated HTML.
    # Only the session owner receives these clickable citations.
    def on_web_sources(payload):
        asyncio.create_task(sio.emit('web_sources', payload, room=sid))

    # Callback to send CAL data to frontend
    def on_cad_data(data):
        info = f"{len(data.get('vertices', []))} vertices" if 'vertices' in data else f"{len(data.get('data', ''))} bytes (STL)"
        print(f"Sending CAD data to frontend: {info}")
        asyncio.create_task(sio.emit('cad_data', data))

    # Callback to send Browser data to frontend
    def on_web_data(data):
        print(f"Sending Browser data to frontend: {len(data.get('log', ''))} chars logs")
        asyncio.create_task(sio.emit('browser_frame', data))
        
    # Callback to send Transcription data to frontend
    def on_transcription(data):
        # data = {"sender": "User"|"ADA", "text": "..."}
        asyncio.create_task(sio.emit('transcription', data))

    # Callback to send Confirmation Request to frontend
    def on_tool_confirmation(data):
        # data = {"id": "uuid", "tool": "tool_name", "args": {...}}
        print(f"Requesting confirmation for tool: {data.get('tool')}")
        # Only the initiating SPARK window may approve a desktop launch.
        asyncio.create_task(sio.emit('tool_confirmation_request', data, room=sid))

    # Callback to send CAD status to frontend
    def on_cad_status(status):
        # status can be: 
        # - a string like "generating" (from ada.py handle_cad_request)
        # - a dict with {status, attempt, max_attempts, error} (from CadAgent)
        if isinstance(status, dict):
            print(f"Sending CAD Status: {status.get('status')} (attempt {status.get('attempt')}/{status.get('max_attempts')})")
            asyncio.create_task(sio.emit('cad_status', status))
        else:
            # Legacy: simple string
            print(f"Sending CAD Status: {status}")
            asyncio.create_task(sio.emit('cad_status', {'status': status}))

    # Callback to send CAD thoughts to frontend (streaming)
    def on_cad_thought(thought_text):
        asyncio.create_task(sio.emit('cad_thought', {'text': thought_text}))

    # Callback to send Project Update to frontend
    def on_project_update(project_name):
        print(f"Sending Project Update: {project_name}")
        asyncio.create_task(sio.emit('project_update', {'project': project_name}))

    # Callback to send Device Update to frontend
    def on_device_update(devices):
        # devices is a list of dicts
        print(f"Sending Kasa Device Update: {len(devices)} devices")
        asyncio.create_task(sio.emit('kasa_devices', devices))

    # Callback to send Error to frontend
    def on_error(msg):
        print(f"Sending Error to frontend: {msg}")
        asyncio.create_task(sio.emit('error', {'msg': msg}))

    # Cinematic one-turn microphone lock is reflected in the real UI state.
    # The backend alone is authoritative for when a user may rearm.
    def on_mic_safety(payload):
        asyncio.create_task(sio.emit('mic_safety', payload))

    # Initialize SPARK Live. A running socket is not proof of provider connection.
    def on_live_status(payload):
        global live_state, live_message
        live_state = payload.get("state", "error")
        live_message = payload.get("message", "")
        asyncio.create_task(sio.emit('ai_status', payload))

    try:
        print(f"Initializing AudioLoop with device_index={device_index}")
        audio_loop = ada.AudioLoop(
            video_mode="none", 
            on_audio_data=on_audio_data,
            on_browser_audio=on_browser_audio if AUDIO_TRANSPORT == "browser_aec" else None,
            on_web_sources=on_web_sources,
            browser_audio=AUDIO_TRANSPORT == "browser_aec",
            on_cad_data=on_cad_data,
            on_web_data=on_web_data,
            on_transcription=on_transcription,
            on_tool_confirmation=on_tool_confirmation,
            on_cad_status=on_cad_status,
            on_cad_thought=on_cad_thought,
            on_project_update=on_project_update,
            on_device_update=on_device_update,
            on_error=on_error,
            on_live_status=on_live_status,
            on_mic_safety=on_mic_safety,

            input_device_index=device_index,
            input_device_name=device_name,
            kasa_agent=kasa_agent
        )
        print("AudioLoop initialized successfully.")

        audio_loop.owner_sid = sid  # Approval ownership even in native fallback.
        audio_loop.browser_ready = False

        # Apply current permissions
        audio_loop.update_permissions(SETTINGS["tool_permissions"])
        
        # Browser mode cannot transmit until the renderer verifies actual AEC.
        if AUDIO_TRANSPORT == "browser_aec":
            audio_loop.set_paused(True)

        # Check initial mute state
        if data and data.get('muted', False):
            print("Starting with Audio Paused")
            audio_loop.set_paused(True)

        live_state = "connecting"
        live_message = "Connecting to Gemini Live..."
        await sio.emit('ai_status', {
            'state': 'connecting', 'model': ada.MODEL,
            'message': 'Opening SPARK Gemini Live session...'})
        print("Creating asyncio task for AudioLoop.run()")
        loop_task = asyncio.create_task(audio_loop.run())
        
        # Add a done callback to catch silent failures in the loop
        def handle_loop_exit(task):
            global live_state, live_message, audio_loop, loop_task
            try:
                task.result()
            except asyncio.CancelledError:
                print("Audio Loop Cancelled")
            except Exception as e:
                print("SPARK Live session terminated; see backend log for details.")
                live_state = "error"
                live_message = "Gemini Live connection or audio session failed."
                asyncio.create_task(sio.emit('ai_status', {
                    'state': 'error', 'model': ada.MODEL,
                    'message': 'SPARK Live audio loop stopped unexpectedly.'}))
            finally:
                if loop_task is task:
                    loop_task = None
                    audio_loop = None
        
        loop_task.add_done_callback(handle_loop_exit)
        
        # Load saved printers
        saved_printers = SETTINGS.get("printers", [])
        if saved_printers and audio_loop.printer_agent:
            print(f"[SERVER] Loading {len(saved_printers)} saved printers...")
            for p in saved_printers:
                audio_loop.printer_agent.add_printer_manually(
                    name=p.get("name", p["host"]),
                    host=p["host"],
                    port=p.get("port", 80),
                    printer_type=p.get("type", "moonraker"),
                    camera_url=p.get("camera_url")
                )
        
        # Start Printer Monitor
        asyncio.create_task(monitor_printers_loop())
        
    except Exception as e:
        print(f"CRITICAL ERROR STARTING ADA: {e}")
        import traceback
        traceback.print_exc()
        live_state = "error"
        live_message = "Gemini Live connection or audio session failed."
        await sio.emit('ai_status', {
            'state': 'error', 'model': ada.MODEL,
            'message': 'SPARK Core could not start its audio engine. Check the backend terminal.'})
        audio_loop = None # Ensure we can try again


async def monitor_printers_loop():
    """Background task to query printer status periodically."""
    print("[SERVER] Starting Printer Monitor Loop")
    while audio_loop and audio_loop.printer_agent:
        try:
            agent = audio_loop.printer_agent
            if not agent.printers:
                await asyncio.sleep(5)
                continue
                
            tasks = []
            for host, printer in agent.printers.items():
                if printer.printer_type.value != "unknown":
                    tasks.append(agent.get_print_status(host))
            
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        pass # Ignore errors for now
                    elif res:
                        # res is PrintStatus object
                        await sio.emit('print_status_update', res.to_dict())
                        
        except asyncio.CancelledError:
            print("[SERVER] Printer Monitor Cancelled")
            break
        except Exception as e:
            print(f"[SERVER] Monitor Loop Error: {e}")
            
        await asyncio.sleep(2) # Update every 2 seconds for responsiveness

@sio.event
async def stop_audio(sid):
    global audio_loop, loop_task, live_state
    if audio_loop:
        audio_loop.stop()
        if loop_task and not loop_task.done():
            loop_task.cancel()  # Cancel old Live socket and all native/browser audio tasks.
        print("Stopping Audio Loop")
        audio_loop = None
        live_state = 'idle'
        await sio.emit('ai_status', live_status(ada.client is not None, ada.MODEL))
        await sio.emit('status', {'msg': 'A.D.A Stopped'})

@sio.event
async def browser_audio_ready(sid, data=None):
    # Media access can fail. Keep mic CLOSED until Chromium reports
    # an active echo-cancelled capture + playback graph.
    if (AUDIO_TRANSPORT != "browser_aec" or not audio_loop
            or not audio_loop.browser_audio or audio_loop.owner_sid != sid
            or not audio_loop.session):
        return
    audio_loop.browser_ready = True
    audio_loop.set_paused(bool(data.get("muted", False)) if isinstance(data, dict) else True)
    await sio.emit('audio_transport_status',
        {'ready': True, 'mode': 'browser_aec', 'muted': audio_loop.paused}, room=sid)


@sio.event
async def browser_audio_error(sid, data=None):
    if audio_loop and audio_loop.browser_audio and audio_loop.owner_sid == sid:
        audio_loop.set_paused(True)
        audio_loop.browser_ready = False
        await sio.emit('audio_transport_status',
            {'ready': False, 'mode': 'browser_aec',
             'message': 'Windows microphone AEC or Chromium speaker is unavailable.'}, room=sid)


@sio.event
async def browser_mic_pcm(sid, payload):
    if (AUDIO_TRANSPORT != "browser_aec" or not audio_loop or
            not audio_loop.browser_audio or audio_loop.owner_sid != sid
            or not audio_loop.session or audio_loop.paused or
            not audio_loop.browser_ready or audio_loop.out_queue is None):
        return
    try:
        pcm = validate_pcm(payload)
        audio_loop.out_queue.put_nowait({'data': pcm, 'mime_type': 'audio/pcm'})
    except (ValueError, asyncio.QueueFull):
        # No oversized, malformed or excessive audio may enter Gemini.
        return


@sio.event
async def pause_audio(sid):
    global audio_loop
    if audio_loop:
        audio_loop.set_paused(True)
        print("Pausing Audio")
        await sio.emit('mic_safety', {'muted': True, 'reason': 'user_muted'})
        await sio.emit('status', {'msg': 'Audio Paused'})

@sio.event
async def resume_audio(sid):
    global audio_loop
    if audio_loop and audio_loop.session:
        if audio_loop.browser_audio:
            # A button may NEVER turn on raw PCM before Chrome verifies AEC.
            if not getattr(audio_loop, "browser_ready", False):
                await sio.emit('audio_transport_status',
                    {'ready': False, 'mode': 'browser_aec',
                     'message': 'Echo cancellation is not ready; microphone remains blocked.'},
                    room=sid)
                return
            audio_loop.set_paused(False)
            await sio.emit('mic_safety', {'muted': False, 'reason': 'aec_enabled'}, room=sid)
            return
        # Never let a click re-enable mic while speaker playback or the
        # acoustic cooldown is still active. Cinematic mode also requires
        # a fresh user gesture after every assistant reply.
        if not audio_loop.echo_gate.rearm():
            await sio.emit('mic_safety', {
                'muted': True, 'reason': 'wait_for_speaker',
                'message': 'SPARK is still speaking. Activate the microphone after the response.'
            }, room=sid)
            return
        audio_loop.set_paused(False)
        print("Resuming Audio")
        await sio.emit('mic_safety', {'muted': False, 'reason': 'user_rearmed'}, room=sid)
        await sio.emit('status', {'msg': 'SPARK microphone resumed'}, room=sid)
    else:
        await sio.emit('ai_status', {
            'state': live_state if live_state in ('error', 'setup_required') else 'disconnected',
            'model': ada.MODEL,
            'message': 'SPARK Live is not connected. Check Gemini key, model and microphone.'}, room=sid)

@sio.event
async def confirm_tool(sid, data):
    # Fail closed: tool approvals belong solely to the initiating cockpit,
    # never any other Socket.IO client on the local port.
    if (not audio_loop or getattr(audio_loop, "owner_sid", None) != sid
            or not isinstance(data, dict)
            or not isinstance(data.get('id'), str)
            or type(data.get('confirmed')) is not bool):
        return
    request_id = data['id']
    confirmed = data['confirmed']
    
    print(f"[SERVER DEBUG] Received confirmation response for {request_id}: {confirmed}")
    
    if audio_loop:
        audio_loop.resolve_tool_confirmation(request_id, confirmed)
    else:
        print("Audio loop not active, cannot resolve confirmation.")

@sio.event
async def shutdown(sid, data=None):
    """Gracefully shutdown the server when the application closes."""
    global audio_loop, loop_task, authenticator
    
    print("[SERVER] ========================================")
    print("[SERVER] SHUTDOWN SIGNAL RECEIVED FROM FRONTEND")
    print("[SERVER] ========================================")
    
    # Stop audio loop
    if audio_loop:
        print("[SERVER] Stopping Audio Loop...")
        audio_loop.stop()
        audio_loop = None
    
    # Cancel the loop task if running
    if loop_task and not loop_task.done():
        print("[SERVER] Cancelling loop task...")
        loop_task.cancel()
        loop_task = None
    
    # Stop authenticator if running
    if authenticator:
        print("[SERVER] Stopping Authenticator...")
        authenticator.stop()
    
    print("[SERVER] Graceful shutdown complete. Terminating process...")
    
    # Force exit immediately - os._exit bypasses cleanup but ensures termination
    os._exit(0)

@sio.event
async def user_input(sid, data):
    text = data.get('text')
    print(f"[SPARK] Received typed input ({len(text or '')} characters)")
    
    if not audio_loop:
        await sio.emit('error', {'msg': 'SPARK Core unavailable. Configure Gemini and reconnect.'}, room=sid)
        return

    if not audio_loop.session:
        await sio.emit('error', {'msg': 'Selected AI provider is not ready.'}, room=sid)
        return

    if text and getattr(audio_loop, "provider", None) == "groq":
        asyncio.create_task(audio_loop.handle_text(text))
        return

    if text:
        print("[SPARK] Sending typed turn to Gemini Live")
        
        # Log User Input to Project History
        if audio_loop and audio_loop.project_manager:
            audio_loop.project_manager.log_chat("User", text)
            
        # Use the currently documented Live SDK client-content interface for
        # finished typed turns; realtime media is a separate input stream.
        try:
            if audio_loop._latest_image_payload:
                frame = audio_loop._latest_image_payload["data"]
                if isinstance(frame, str):
                    import base64
                    frame = base64.b64decode(frame)
                await audio_loop.session.send_realtime_input(
                    video=ada.types.Blob(data=frame, mime_type="image/jpeg"))
            await audio_loop.session.send_client_content(
                turns={"role": "user", "parts": [{"text": text}]}, turn_complete=True)
        except Exception:
            await sio.emit('error', {
                'msg': 'Could not send text to Gemini Live. The session may have closed.'}, room=sid)

import json
from datetime import datetime
from pathlib import Path

# ... (imports)

@sio.event
async def video_frame(sid, data):
    # Camera requires an explicitly started Live session and an authenticated
    # user when facial authentication has been enabled.
    if not audio_loop or not audio_loop.session:
        return
    if SETTINGS.get("face_auth_enabled", False) and (
        not authenticator or not authenticator.authenticated
    ):
        return
    from spark_camera_frames import validate_camera_frame
    try:
        frame = validate_camera_frame(data.get("image") if isinstance(data, dict) else None)
    except ValueError:
        await sio.emit('error', {'msg': 'Rejected invalid or oversized camera frame.'}, room=sid)
        return
    await audio_loop.send_frame(frame)

@sio.event
async def save_memory(sid, data):
    try:
        messages = data.get('messages', [])
        if not messages:
            print("No messages to save.")
            return

        # Ensure directory exists
        memory_dir = Path("long_term_memory")
        memory_dir.mkdir(exist_ok=True)

        # Generate filename
        # Use provided filename if available, else timestamp
        provided_name = data.get('filename')
        
        if provided_name:
            # Simple sanitization
            if not provided_name.endswith('.txt'):
                provided_name += '.txt'
            # Prevent directory traversal
            filename = memory_dir / Path(provided_name).name 
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = memory_dir / f"memory_{timestamp}.txt"

        # Write to file
        with open(filename, 'w', encoding='utf-8') as f:
            for msg in messages:
                sender = msg.get('sender', 'Unknown')
                text = msg.get('text', '')
        print(f"Conversation saved to {filename}")
        await sio.emit('status', {'msg': 'Memory Saved Successfully'})

    except Exception as e:
        print(f"Error saving memory: {e}")
        await sio.emit('error', {'msg': f"Failed to save memory: {str(e)}"})

@sio.event
async def upload_memory(sid, data):
    print(f"Received memory upload request")
    try:
        memory_text = data.get('memory', '')
        if not memory_text:
            print("No memory data provided.")
            return

        if not audio_loop:
             print("[SERVER DEBUG] [Error] Audio loop is None. Cannot load memory.")
             await sio.emit('error', {'msg': "System not ready (Audio Loop inactive)"})
             return
        
        if not audio_loop.session:
             print("[SERVER DEBUG] [Error] Session is None. Cannot load memory.")
             await sio.emit('error', {'msg': "System not ready (No active session)"})
             return

        # Send to model
        print("Sending memory context to model...")
        context_msg = f"System Notification: The user has uploaded a long-term memory file. Please load the following context into your understanding. The format is a text log of previous conversations:\n\n{memory_text}"
        
        await audio_loop.session.send(input=context_msg, end_of_turn=True)
        print("Memory context sent successfully.")
        await sio.emit('status', {'msg': 'Memory Loaded into Context'})

    except Exception as e:
        print(f"Error uploading memory: {e}")
        await sio.emit('error', {'msg': f"Failed to upload memory: {str(e)}"})

@sio.event
async def discover_kasa(sid):
    print(f"Received discover_kasa request")
    try:
        devices = await kasa_agent.discover_devices()
        await sio.emit('kasa_devices', devices)
        await sio.emit('status', {'msg': f"Found {len(devices)} Kasa devices"})
        
        # Save to settings
        # devices is a list of full device info dicts. minimizing for storage.
        saved_devices = []
        for d in devices:
            saved_devices.append({
                "ip": d["ip"],
                "alias": d["alias"],
                "model": d["model"]
            })
        
        # Merge with existing to preserve any manual overrides? 
        # For now, just overwrite with latest scan result + previously known if we want to be fancy,
        # but user asked for "Any new devices that are scanned are added there".
        # A simple full persistence of current state is safest.
        SETTINGS["kasa_devices"] = saved_devices
        save_settings()
        print(f"[SERVER] Saved {len(saved_devices)} Kasa devices to settings.")
        
    except Exception as e:
        print(f"Error discovering kasa: {e}")
        await sio.emit('error', {'msg': f"Kasa Discovery Failed: {str(e)}"})

@sio.event
async def iterate_cad(sid, data):
    # data: { prompt: "make it bigger" }
    prompt = data.get('prompt')
    print(f"Received iterate_cad request: '{prompt}'")
    
    if not audio_loop or not audio_loop.cad_agent:
        await sio.emit('error', {'msg': "CAD Agent not available"})
        return

    try:
        # Notify user work has started
        await sio.emit('status', {'msg': 'Iterating design...'})
        await sio.emit('cad_status', {'status': 'generating'})
        
        # Call the agent with project path
        cad_output_dir = str(audio_loop.project_manager.get_current_project_path() / "cad")
        result = await audio_loop.cad_agent.iterate_prototype(prompt, output_dir=cad_output_dir)
        
        if result:
            info = f"{len(result.get('data', ''))} bytes (STL)"
            print(f"Sending updated CAD data: {info}")
            await sio.emit('cad_data', result)
            # Save to Project
            if 'file_path' in result:
                saved_path = audio_loop.project_manager.save_cad_artifact(result['file_path'], prompt)
                if saved_path:
                    print(f"[SERVER] Saved iterated CAD to {saved_path}")

            await sio.emit('status', {'msg': 'Design updated'})
        else:
            await sio.emit('error', {'msg': 'Failed to update design'})
            
    except Exception as e:
        print(f"Error iterating CAD: {e}")
        await sio.emit('error', {'msg': f"Iteration Error: {str(e)}"})

@sio.event
async def generate_cad(sid, data):
    # data: { prompt: "make a cube" }
    prompt = data.get('prompt')
    print(f"Received generate_cad request: '{prompt}'")
    
    if not audio_loop or not audio_loop.cad_agent:
        await sio.emit('error', {'msg': "CAD Agent not available"})
        return

    try:
        await sio.emit('status', {'msg': 'Generating new design...'})
        await sio.emit('cad_status', {'status': 'generating'})
        
        # Use generate_prototype based on prompt with project path
        cad_output_dir = str(audio_loop.project_manager.get_current_project_path() / "cad")
        result = await audio_loop.cad_agent.generate_prototype(prompt, output_dir=cad_output_dir)
        
        if result:
            info = f"{len(result.get('data', ''))} bytes (STL)"
            print(f"Sending newly generated CAD data: {info}")
            await sio.emit('cad_data', result)


            # Save to Project
            if 'file_path' in result:
                saved_path = audio_loop.project_manager.save_cad_artifact(result['file_path'], prompt)
                if saved_path:
                    print(f"[SERVER] Saved generated CAD to {saved_path}")

            await sio.emit('status', {'msg': 'Design generated'})
        else:
            await sio.emit('error', {'msg': 'Failed to generate design'})
            
    except Exception as e:
        print(f"Error generating CAD: {e}")
        await sio.emit('error', {'msg': f"Generation Error: {str(e)}"})

@sio.event
async def prompt_web_agent(sid, data):
    # data: { prompt: "find xyz" }
    prompt = data.get('prompt')
    print(f"Received web agent prompt: '{prompt}'")
    
    if not audio_loop or not audio_loop.web_agent:
        await sio.emit('error', {'msg': "Web Agent not available"})
        return

    try:
        await sio.emit('status', {'msg': 'Web Agent running...'})
        
        # We assume web_agent has a run method or similar.
        # This might block the loop if not strictly async or offloaded.
        # Ideally web_agent.run is async.
        # And it should emit 'browser_snap' and logs automatically via hooks if setup.
        
        # We might need to launch this as a task if it's long running?
        # asyncio.create_task(audio_loop.web_agent.run(prompt))
        # But we want to catch errors here.
        
        # Based on typical agent design, run() is the entry point.
        await audio_loop.web_agent.run(prompt)
        
        await sio.emit('status', {'msg': 'Web Agent finished'})
        
    except Exception as e:
        print(f"Error running Web Agent: {e}")
        await sio.emit('error', {'msg': f"Web Agent Error: {str(e)}"})

@sio.event
async def discover_printers(sid):
    print("Received discover_printers request")
    
    # If audio_loop isn't ready yet, return saved printers from settings
    if not audio_loop or not audio_loop.printer_agent:
        saved_printers = SETTINGS.get("printers", [])
        if saved_printers:
            # Convert saved printers to the expected format
            printer_list = []
            for p in saved_printers:
                printer_list.append({
                    "name": p.get("name", p["host"]),
                    "host": p["host"],
                    "port": p.get("port", 80),
                    "printer_type": p.get("type", "unknown"),
                    "camera_url": p.get("camera_url")
                })
            print(f"[SERVER] Returning {len(printer_list)} saved printers (audio_loop not ready)")
            await sio.emit('printer_list', printer_list)
            return
        else:
            await sio.emit('printer_list', [])
            await sio.emit('status', {'msg': "Connect to A.D.A to enable printer discovery"})
            return
        
    try:
        printers = await audio_loop.printer_agent.discover_printers()
        await sio.emit('printer_list', printers)
        await sio.emit('status', {'msg': f"Found {len(printers)} printers"})
    except Exception as e:
        print(f"Error discovering printers: {e}")
        await sio.emit('error', {'msg': f"Printer Discovery Failed: {str(e)}"})

@sio.event
async def add_printer(sid, data):
    # data: { host: "192.168.1.50", name: "My Printer", type: "moonraker" }
    raw_host = data.get('host')
    name = data.get('name') or raw_host
    ptype = data.get('type', "moonraker")
    
    # Parse port if present
    if ":" in raw_host:
        host, port_str = raw_host.split(":")
        port = int(port_str)
    else:
        host = raw_host
        port = 80
    
    print(f"Received add_printer request: {host}:{port} ({ptype})")
    
    if not audio_loop or not audio_loop.printer_agent:
        await sio.emit('error', {'msg': "Printer Agent not available"})
        return
        
    try:
        # Add manually
        camera_url = data.get('camera_url')
        printer = audio_loop.printer_agent.add_printer_manually(name, host, port=port, printer_type=ptype, camera_url=camera_url)
        
        # Save to settings
        new_printer_config = {
            "name": name,
            "host": host,
            "port": port,
            "type": ptype,
            "camera_url": camera_url
        }
        
        # Check if already exists to avoid duplicates
        exists = False
        for p in SETTINGS.get("printers", []):
            if p["host"] == host and p["port"] == port:
                exists = True
                break
        
        if not exists:
            if "printers" not in SETTINGS:
                SETTINGS["printers"] = []
            SETTINGS["printers"].append(new_printer_config)
            save_settings()
            print(f"[SERVER] Saved printer {name} to settings.")
        
        # Probe to confirm/correct type
        print(f"Probing {host} to confirm type...")
        # Try port 7125 (Moonraker) and 4408 (Fluidd/K1) 
        ports_to_try = [80, 7125, 4408]
        
        actual_type = "unknown"
        for port in ports_to_try:
             found_type = await audio_loop.printer_agent._probe_printer_type(host, port)
             if found_type.value != "unknown":
                 actual_type = found_type
                 # Update port if different
                 if port != 80:
                     printer.port = port
                 break
        
        if actual_type != "unknown" and actual_type != printer.printer_type:
             printer.printer_type = actual_type
             print(f"Corrected type to {actual_type.value} on port {printer.port}")
             
        # Refresh list for everyone
        printers = [p.to_dict() for p in audio_loop.printer_agent.printers.values()]
        await sio.emit('printer_list', printers)
        await sio.emit('status', {'msg': f"Added printer: {name}"})
        
    except Exception as e:
        print(f"Error adding printer: {e}")
        await sio.emit('error', {'msg': f"Failed to add printer: {str(e)}"})

@sio.event
async def print_stl(sid, data):
    print(f"Received print_stl request: {data}")
    # data: { stl_path: "path/to.stl" | "current", printer: "name_or_ip", profile: "optional" }
    
    if not audio_loop or not audio_loop.printer_agent:
        await sio.emit('error', {'msg': "Printer Agent not available"})
        return
        
    try:
        stl_path = data.get('stl_path', 'current')
        printer_name = data.get('printer')
        profile = data.get('profile')
        
        if not printer_name:
             await sio.emit('error', {'msg': "No printer specified"})
             return
             
        await sio.emit('status', {'msg': f"Preparing print for {printer_name}..."})
        
        # Get current project path for resolution
        current_project_path = None
        if audio_loop and audio_loop.project_manager:
            current_project_path = str(audio_loop.project_manager.get_current_project_path())
            print(f"[SERVER DEBUG] Using project path: {current_project_path}")

        # Resolve STL path before slicing so we can preview it
        resolved_stl = audio_loop.printer_agent._resolve_file_path(stl_path, current_project_path)
        
        if resolved_stl and os.path.exists(resolved_stl):
            # Open the STL in the CAD module for preview
            try:
                import base64
                with open(resolved_stl, 'rb') as f:
                    stl_data = f.read()
                stl_b64 = base64.b64encode(stl_data).decode('utf-8')
                stl_filename = os.path.basename(resolved_stl)
                
                print(f"[SERVER] Opening STL in CAD module: {stl_filename}")
                await sio.emit('cad_data', {
                    'format': 'stl',
                    'data': stl_b64,
                    'filename': stl_filename
                })
            except Exception as e:
                print(f"[SERVER] Warning: Could not preview STL: {e}")
        
        # Progress Callback
        async def on_slicing_progress(percent, message):
            await sio.emit('slicing_progress', {
                'printer': printer_name,
                'percent': percent,
                'message': message
            })
            if percent < 100:
                 await sio.emit('status', {'msg': f"Slicing: {percent}%"})

        result = await audio_loop.printer_agent.print_stl(
            stl_path, 
            printer_name, 
            profile,
            progress_callback=on_slicing_progress,
            root_path=current_project_path
        )
        
        await sio.emit('print_result', result)
        await sio.emit('status', {'msg': f"Print Job: {result.get('status', 'unknown')}"})
        
    except Exception as e:
        print(f"Error printing STL: {e}")
        await sio.emit('error', {'msg': f"Print Failed: {str(e)}"})

@sio.event
async def get_slicer_profiles(sid):
    """Get available OrcaSlicer profiles for manual selection."""
    print("Received get_slicer_profiles request")
    if not audio_loop or not audio_loop.printer_agent:
        await sio.emit('error', {'msg': "Printer Agent not available"})
        return
    
    try:
        profiles = audio_loop.printer_agent.get_available_profiles()
        await sio.emit('slicer_profiles', profiles)
    except Exception as e:
        print(f"Error getting slicer profiles: {e}")
        await sio.emit('error', {'msg': f"Failed to get profiles: {str(e)}"})

@sio.event
async def control_kasa(sid, data):
    # data: { ip, action: "on"|"off"|"brightness"|"color", value: ... }
    ip = data.get('ip')
    action = data.get('action')
    print(f"Kasa Control: {ip} -> {action}")
    
    try:
        success = False
        if action == "on":
            success = await kasa_agent.turn_on(ip)
        elif action == "off":
            success = await kasa_agent.turn_off(ip)
        elif action == "brightness":
            val = data.get('value')
            success = await kasa_agent.set_brightness(ip, val)
        elif action == "color":
            # value is {h, s, v} - convert to tuple for set_color
            h = data.get('value', {}).get('h', 0)
            s = data.get('value', {}).get('s', 100)
            v = data.get('value', {}).get('v', 100)
            success = await kasa_agent.set_color(ip, (h, s, v))
        
        if success:
            await sio.emit('kasa_update', {
                'ip': ip,
                'is_on': True if action == "on" else (False if action == "off" else None),
                'brightness': data.get('value') if action == "brightness" else None,
            })
 
        else:
             await sio.emit('error', {'msg': f"Failed to control device {ip}"})

    except Exception as e:
         print(f"Error controlling kasa: {e}")
         await sio.emit('error', {'msg': f"Kasa Control Error: {str(e)}"})

@sio.event
async def get_settings(sid):
    await sio.emit('settings', SETTINGS)

@sio.event
async def update_settings(sid, data):
    # Generic update
    print(f"Updating settings: {data}")
    
    # Handle specific keys if needed
    if "tool_permissions" in data:
        SETTINGS["tool_permissions"].update(data["tool_permissions"])
        if audio_loop:
            audio_loop.update_permissions(SETTINGS["tool_permissions"])
            
    if "face_auth_enabled" in data:
        SETTINGS["face_auth_enabled"] = data["face_auth_enabled"]
        # If turned OFF, maybe emit auth status true?
        if not data["face_auth_enabled"]:
             await sio.emit('auth_status', {'authenticated': True})
             # Stop auth loop if running?
             if authenticator:
                 authenticator.stop() 

    if "camera_flipped" in data:
        SETTINGS["camera_flipped"] = data["camera_flipped"]
        print(f"[SERVER] Camera flip set to: {data['camera_flipped']}")

    save_settings()
    # Broadcast new full settings
    await sio.emit('settings', SETTINGS)


# Deprecated/Mapped for compatibility if frontend still uses specific events
@sio.event
async def get_tool_permissions(sid):
    await sio.emit('tool_permissions', SETTINGS["tool_permissions"])

@sio.event
async def update_tool_permissions(sid, data):
    print(f"Updating permissions (legacy event): {data}")
    SETTINGS["tool_permissions"].update(data)
    save_settings()
    
    if audio_loop:
        audio_loop.update_permissions(SETTINGS["tool_permissions"])
    # Broadcast update to all
    await sio.emit('tool_permissions', SETTINGS["tool_permissions"])

if __name__ == "__main__":
    uvicorn.run(
        "server:app_socketio", 
        host="127.0.0.1", 
        port=8000, 
        reload=False, # Reload enabled causes spawn of worker which might miss the event loop policy patch
        loop="asyncio",
        reload_excludes=["temp_cad_gen.py", "output.stl", "*.stl"]
    )
