import asyncio
import base64
import io
import os
import sys
import traceback
from dotenv import load_dotenv
from pathlib import Path
from spark_live_config import live_model, live_error_message, live_error_requires_user_action
from spark_live_profile import live_profile, select_live_config
from spark_pc_access import pc_live_config
from spark_jarvis import jarvis_live_config
from spark_workbench_voice import parse_workbench_command
from spark_echo_gate import EchoGate
import cv2
import pyaudio
import PIL.Image
import mss
import argparse
import math
import struct
import time

from google import genai
from google.genai import types

if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup
    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

from tools import tools_list
from spark_desktop import launch_allowed_app
from spark_grounding import extract_grounding_sources
from spark_cinematic_tools import allowed_live_tool, tool_confirmation_required, get_system_status

FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

MODEL = live_model()
DEFAULT_MODE = "camera"

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))
client = genai.Client(http_options={"api_version": "v1beta"}, api_key=os.getenv("GEMINI_API_KEY")) if os.getenv("GEMINI_API_KEY") else None

# Function definitions
generate_cad = {
    "name": "generate_cad",
    "description": "Generates a 3D CAD model based on a prompt.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "The description of the object to generate."}
        },
        "required": ["prompt"]
    },
    "behavior": "NON_BLOCKING"
}

run_web_agent = {
    "name": "run_web_agent",
    "description": "Opens a web browser and performs a task according to the prompt.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "The detailed instructions for the web browser agent."}
        },
        "required": ["prompt"]
    },
    "behavior": "NON_BLOCKING"
}

create_project_tool = {
    "name": "create_project",
    "description": "Creates a new project folder to organize files.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING", "description": "The name of the new project."}
        },
        "required": ["name"]
    }
}

switch_project_tool = {
    "name": "switch_project",
    "description": "Switches the current active project context.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING", "description": "The name of the project to switch to."}
        },
        "required": ["name"]
    }
}

list_projects_tool = {
    "name": "list_projects",
    "description": "Lists all available projects.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    }
}

list_smart_devices_tool = {
    "name": "list_smart_devices",
    "description": "Lists all available smart home devices (lights, plugs, etc.) on the network.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    }
}

control_light_tool = {
    "name": "control_light",
    "description": "Controls a smart light device.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target": {
                "type": "STRING",
                "description": "The IP address of the device to control. Always prefer the IP address over the alias for reliability."
            },
            "action": {
                "type": "STRING",
                "description": "The action to perform: 'turn_on', 'turn_off', or 'set'."
            },
            "brightness": {
                "type": "INTEGER",
                "description": "Optional brightness level (0-100)."
            },
            "color": {
                "type": "STRING",
                "description": "Optional color name (e.g., 'red', 'cool white') or 'warm'."
            }
        },
        "required": ["target", "action"]
    }
}

discover_printers_tool = {
    "name": "discover_printers",
    "description": "Discovers 3D printers available on the local network.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    }
}

print_stl_tool = {
    "name": "print_stl",
    "description": "Prints an STL file to a 3D printer. Handles slicing the STL to G-code and uploading to the printer.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "stl_path": {"type": "STRING", "description": "Path to STL file, or 'current' for the most recent CAD model."},
            "printer": {"type": "STRING", "description": "Printer name or IP address."},
            "profile": {"type": "STRING", "description": "Optional slicer profile name."}
        },
        "required": ["stl_path", "printer"]
    }
}

get_print_status_tool = {
    "name": "get_print_status",
    "description": "Gets the current status of a 3D printer including progress, time remaining, and temperatures.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "printer": {"type": "STRING", "description": "Printer name or IP address."}
        },
        "required": ["printer"]
    }
}

iterate_cad_tool = {
    "name": "iterate_cad",
    "description": "Modifies or iterates on the current CAD design based on user feedback. Use this when the user asks to adjust, change, modify, or iterate on the existing 3D model (e.g., 'make it taller', 'add a handle', 'reduce the thickness').",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "The changes or modifications to apply to the current design."}
        },
        "required": ["prompt"]
    },
    "behavior": "NON_BLOCKING"
}

tools = [{'google_search': {}}, {"function_declarations": [generate_cad, run_web_agent, create_project_tool, switch_project_tool, list_projects_tool, list_smart_devices_tool, control_light_tool, discover_printers_tool, print_stl_tool, get_print_status_tool, iterate_cad_tool, {"name": "launch_desktop_app", "description": "Open one of these approved Windows applications after user confirmation: notepad, calculator, paint.", "parameters": {"type": "OBJECT", "properties": {"app": {"type": "STRING", "description": "One of: notepad, calculator, paint"}}, "required": ["app"]}}] + tools_list[0]['function_declarations'][1:]}]

# --- CONFIG UPDATE: Enabled Transcription ---
config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    # We switch these from [] to {} to enable them with default settings
    output_audio_transcription={}, 
    input_audio_transcription={},
    system_instruction="Your name is SPARK, the voice and reasoning core of the SPARK workstation. "
        "You can converse naturally with the user and assist with available approved tools. "
        "When answering, respond using complete and concise sentences to keep a quick pacing and keep the conversation flowing. "
        "You have a fun personality.",
    tools=tools,
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name="Kore"
            )
        )
    )
)

# Voice mode reproduces the known-good minimal Gemini handshake, leaving
# all original tools and transcription available in explicitly selected full mode.
config = select_live_config(live_profile(), config)

pya = pyaudio.PyAudio()

from cad_agent import CadAgent
from web_agent import WebAgent
from kasa_agent import KasaAgent
from printer_agent import PrinterAgent

# Read-only MCP services reachable from voice, declared once so that every entry
# gets the same argument bound, the same call budget and the same cache lifetime.
# One bounded string argument each: a Live tool that takes more than that is more
# likely to be filled in wrongly by the model than to be used well.
MCP_VOICE_TOOLS = {
    "query_spark_graph": {
        "argument": "question", "minimum": 1, "maximum": 220,
        "label": "Graphify", "callback": "on_graphify_query", "timeout": 45},
    "search_spark_timeline": {
        "argument": "question", "minimum": 3, "maximum": 220,
        "label": "Graphiti", "callback": "on_graphiti_query", "timeout": 45},
    "get_spark_entity_history": {
        "argument": "entity", "minimum": 1, "maximum": 120,
        "label": "Graphiti", "callback": "on_graphiti_entity", "timeout": 45},
    "ask_hermes_experience": {
        "argument": "kind", "choices": ("skills", "memories", "status"),
        "label": "Hermes", "callback": "on_hermes_query", "timeout": 45},
    "search_obsidian_notes": {
        "argument": "query", "minimum": 1, "maximum": 120,
        "label": "Obsidian", "callback": "on_obsidian_search", "timeout": 30},
}
MCP_VOICE_BUDGET = 3
MCP_VOICE_WINDOW = 60

class AudioLoop:
    pc_access = None
    jarvis_access = None
    def __init__(self, video_mode=DEFAULT_MODE, on_audio_data=None, on_video_frame=None, on_cad_data=None, on_web_data=None, on_transcription=None, on_tool_confirmation=None, on_cad_status=None, on_cad_thought=None, on_project_update=None, on_device_update=None, on_error=None, on_live_status=None, on_mic_safety=None, on_browser_audio=None, on_web_sources=None, browser_audio=False, input_device_index=None, input_device_name=None, output_device_index=None, kasa_agent=None, on_graphify_query=None, on_graphiti_query=None, on_graphiti_entity=None, on_hermes_query=None, on_obsidian_search=None):
        self.video_mode = video_mode
        self.on_audio_data = on_audio_data
        self.on_video_frame = on_video_frame
        self.on_cad_data = on_cad_data
        self.on_web_data = on_web_data
        self.on_transcription = on_transcription
        self.on_tool_confirmation = on_tool_confirmation 
        self.on_cad_status = on_cad_status
        self.on_cad_thought = on_cad_thought
        self.on_project_update = on_project_update
        self.on_device_update = on_device_update
        self.on_error = on_error
        self.on_live_status = on_live_status
        self.on_mic_safety = on_mic_safety
        self.on_browser_audio = on_browser_audio
        self.on_web_sources = on_web_sources
        self.on_graphify_query = on_graphify_query
        self.on_graphiti_query = on_graphiti_query
        self.on_graphiti_entity = on_graphiti_entity
        self.on_hermes_query = on_hermes_query
        self.on_obsidian_search = on_obsidian_search
        # Per-tool call timestamps and per-(tool, argument) answers, both bounded
        # to MCP_VOICE_WINDOW seconds.
        self._mcp_calls = {}
        self._mcp_cache = {}
        # Deterministic architecture routing: accumulate the user's utterance
        # and dispatch once per turn, independent of model tool choice.
        self._user_utterance = ""
        self._graphify_dispatched = False
        self._graphify_tool_used = False
        self._graphiti_dispatched = False
        self._grounding_signature = None
        self.browser_audio = bool(browser_audio)
        self.input_device_index = input_device_index
        self.input_device_name = input_device_name
        self.output_device_index = output_device_index

        self.audio_in_queue = None
        self.out_queue = None
        self.paused = False
        # Silence microphone transport while the assistant speaks to prevent
        # acoustic self-feedback from loudspeakers (half-duplex by design).
        self.echo_gate = EchoGate(require_rearm=live_profile() == "cinematic")

        self.chat_buffer = {"sender": None, "text": ""} # For aggregating chunks
        
        # Track last transcription text to calculate deltas (Gemini sends cumulative text)
        self._last_input_transcription = ""
        self._last_output_transcription = ""

        self.audio_in_queue = None
        self.out_queue = None
        self.paused = False

        self.session = None
        
        # Create CadAgent with thought callback
        def handle_cad_thought(thought_text):
            if self.on_cad_thought:
                self.on_cad_thought(thought_text)
        
        def handle_cad_status(status_info):
            if self.on_cad_status:
                self.on_cad_status(status_info)
        
        self.cad_agent = CadAgent(on_thought=handle_cad_thought, on_status=handle_cad_status) if client else None
        self.web_agent = WebAgent() if client else None
        self.kasa_agent = kasa_agent if kasa_agent else KasaAgent()
        self.printer_agent = PrinterAgent()

        self.send_text_task = None
        self.stop_event = asyncio.Event()
        
        self.stop_event = asyncio.Event()
        
        self.permissions = {} # Default Empty (Will treat unset as True)
        self._pending_confirmations = {}

        # Video buffering state
        self._latest_image_payload = None
        # VAD State
        self._is_speaking = False
        self._silence_start_time = None
        
        # Initialize ProjectManager
        from project_manager import ProjectManager
        # Assuming we are running from backend/ or root? 
        # Using abspath of current file to find root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # If ada.py is in backend/, project root is one up
        project_root = os.path.dirname(current_dir)
        self.project_manager = ProjectManager(project_root)
        
        # Sync Initial Project State
        if self.on_project_update:
            # We need to defer this slightly or just call it. 
            # Since this is init, loop might not be running, but on_project_update in server.py uses asyncio.create_task which needs a loop.
            # We will handle this by calling it in run() or just print for now.
            pass

    def flush_chat(self):
        """Forces the current chat buffer to be written to log."""
        if self.chat_buffer["sender"] and self.chat_buffer["text"].strip():
            self.project_manager.log_chat(self.chat_buffer["sender"], self.chat_buffer["text"])
            self.chat_buffer = {"sender": None, "text": ""}
        # Reset transcription tracking for new turn
        self._last_input_transcription = ""
        self._last_output_transcription = ""

    async def answer_mcp_tool(self, name, args):
        """Validate, budget and cache one read-only MCP voice tool call.

        Always returns a sentence rather than raising: the model asked for a tool
        call, so it needs a function response even when the argument is bad, the
        service is unconfigured, or the call fails.
        """
        spec = MCP_VOICE_TOOLS[name]
        label = spec["label"]
        value = (args if isinstance(args, dict) else {}).get(spec["argument"])
        now = time.monotonic()

        choices = spec.get("choices")
        if choices:
            if not isinstance(value, str) or value.strip().lower() not in choices:
                return f"{label} needs one of: {', '.join(choices)}."
            argument_value = key = value.strip().lower()
        else:
            if not isinstance(value, str) or not spec["minimum"] <= len(value.strip()) <= spec["maximum"]:
                return f"Invalid {label} request."
            argument_value = value.strip()
            key = " ".join(argument_value.lower().split())

        callback = getattr(self, spec["callback"], None)
        if callback is None:
            return f"{label} is not configured for this session."

        calls = [t for t in self._mcp_calls.get(name, ()) if now - t < MCP_VOICE_WINDOW]
        self._mcp_calls[name] = calls
        self._mcp_cache = {
            k: v for k, v in self._mcp_cache.items()
            if now - v[0] < MCP_VOICE_WINDOW
        }

        cached = self._mcp_cache.get((name, key))
        if cached is not None:
            return cached[1]
        if len(calls) >= MCP_VOICE_BUDGET:
            return f"{label} rate limit reached for this voice session."

        calls.append(now)
        try:
            answer = await asyncio.wait_for(callback(argument_value), timeout=spec["timeout"])
        except Exception:
            answer = f"{label} query failed."
        if not isinstance(answer, str) or not answer.strip():
            answer = f"{label} returned no result."
        # Failures are cached too, so one broken service cannot be retried
        # against a live microphone for the rest of the window.
        self._mcp_cache[(name, key)] = (now, answer)
        return answer

    async def maybe_dispatch_graphify(self, session):
        """Deterministic architecture routing for the Gemini Live path.

        The Live model is free to ignore its query_spark_graph tool. When the
        user's completed utterance is an explicit architecture question we call
        Graphify ourselves and inject the evidence as a client turn, so the
        answer is grounded in the local graph regardless of model choice.

        If the model already called query_spark_graph for this turn, skip: the
        tool response is authoritative and avoids a duplicate spoken answer.
        """
        if self._graphify_dispatched:
            return
        if (self.on_graphify_query is None and self.on_graphiti_query is None
                and self.on_obsidian_search is None):
            return
        if self._graphify_tool_used:
            self._graphify_dispatched = True
            return
        utterance = self._user_utterance.strip()
        if not utterance:
            return
        command = parse_workbench_command(utterance)
        if not command:
            return
        if command.get("action") == "graphify_voice_query":
            self._graphify_dispatched = True
            self._graphiti_dispatched = True
            question = command["payload"]["question"]
            try:
                answer = await asyncio.wait_for(
                    self.on_graphify_query(question), timeout=45
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                answer = "Graphify MCP unavailable or timed out."
            except Exception:
                return
            if not isinstance(answer, str) or not answer.strip():
                return
            try:
                await session.send_client_content(
                    turns={"role": "user", "parts": [{
                        "text": (
                            "The user asked an architecture question. Summarise the "
                            "answer in one or two spoken sentences using ONLY this "
                            "verified Graphify evidence, naming the relevant files. "
                            "Do not read the raw node list aloud.\n\n" + answer[:1800]
                        )
                    }]},
                    turn_complete=True,
                )
            except Exception:
                pass
            return
        if command.get("action") == "graphiti_voice_query" and self.on_graphiti_query:
            self._graphiti_dispatched = True
            self._graphify_dispatched = True
            question = command["payload"]["question"]
            try:
                answer = await asyncio.wait_for(
                    self.on_graphiti_query(question), timeout=45
                )
            except Exception:
                return
            if not isinstance(answer, str) or not answer.strip():
                return
            try:
                await session.send_client_content(
                    turns={"role": "user", "parts": [{
                        "text": (
                            "The user asked about their recorded project history. "
                            "Summarise the answer in one or two spoken sentences using "
                            "ONLY this Graphiti evidence. Note if facts were superseded. "
                            "Say plainly if nothing was found.\n\n" + answer[:1800]
                        )
                    }]},
                    turn_complete=True,
                )
            except Exception:
                pass
            return
        if command.get("action") == "graphiti_entity_history" and self.on_graphiti_entity:
            self._graphiti_dispatched = True
            self._graphify_dispatched = True
            entity = command["payload"]["entity"]
            try:
                answer = await asyncio.wait_for(
                    self.on_graphiti_entity(entity), timeout=45
                )
            except Exception:
                return
            if not isinstance(answer, str) or not answer.strip():
                return
            try:
                await session.send_client_content(
                    turns={"role": "user", "parts": [{
                        "text": (
                            "The user asked for history about a named thing. Summarise "
                            "in one or two spoken sentences using ONLY this Graphiti "
                            "timeline. Report superseded facts as superseded. Say "
                            "plainly if nothing was found.\n\n" + answer[:1800]
                        )
                    }]},
                    turn_complete=True,
                )
            except Exception:
                pass
            return
        if command.get("action") == "obsidian_search" and self.on_obsidian_search:
            self._graphify_dispatched = True
            self._graphiti_dispatched = True
            query = command["payload"]["query"]
            try:
                answer = await asyncio.wait_for(
                    self.on_obsidian_search(query), timeout=30
                )
            except Exception:
                return
            if not isinstance(answer, str) or not answer.strip():
                return
            try:
                await session.send_client_content(
                    turns={"role": "user", "parts": [{
                        "text": (
                            "The user searched their local Obsidian vault. Summarise "
                            "the result in one spoken sentence using ONLY this evidence.\n\n"
                            + answer[:1800]
                        )
                    }]},
                    turn_complete=True,
                )
            except Exception:
                pass
            return

    def update_permissions(self, new_perms):
        print(f"[ADA DEBUG] [CONFIG] Updating tool permissions: {new_perms}")
        self.permissions.update(new_perms)

    def set_paused(self, paused):
        self.paused = paused

    def stop(self):
        self.stop_event.set()
        
    def resolve_tool_confirmation(self, request_id, confirmed):
        print(f"[ADA DEBUG] [RESOLVE] resolve_tool_confirmation called. ID: {request_id}, Confirmed: {confirmed}")
        if request_id in self._pending_confirmations:
            future = self._pending_confirmations[request_id]
            if not future.done():
                print(f"[ADA DEBUG] [RESOLVE] Future found and pending. Setting result to: {confirmed}")
                future.set_result(confirmed)
            else:
                 print(f"[ADA DEBUG] [WARN] Request {request_id} future already done. Result: {future.result()}")
        else:
            print(f"[ADA DEBUG] [WARN] Confirmation Request {request_id} not found in pending dict. Keys: {list(self._pending_confirmations.keys())}")

    def clear_audio_queue(self):
        """Clears the queue of pending audio chunks to stop playback immediately."""
        try:
            count = 0
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()
                count += 1
            if count > 0:
                print(f"[ADA DEBUG] [AUDIO] Cleared {count} chunks from playback queue due to interruption.")
        except Exception as e:
            print(f"[ADA DEBUG] [ERR] Failed to clear audio queue: {e}")

    async def send_frame(self, frame_data):
        # Update the latest frame payload
        if isinstance(frame_data, bytes):
            b64_data = base64.b64encode(frame_data).decode('utf-8')
        else:
            b64_data = frame_data 

        # Keep the latest image for speech-triggered refreshes, but do not
        # require voice activity to deliver the first scene to Gemini.
        self._latest_image_payload = {"mime_type": "image/jpeg", "data": b64_data}
        if self.out_queue is not None and self.session is not None:
            try:
                self.out_queue.put_nowait(self._latest_image_payload)
            except asyncio.QueueFull:
                # Camera must never stall or displace real-time speech.
                pass

    async def send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            if msg.get("mime_type", "").startswith("audio/pcm"):
                # Second boundary: discard frames queued just before model
                # speech started; the capture gate alone is not sufficient.
                if self.paused or (not self.browser_audio and self.echo_gate.mic_blocked()):
                    continue
                await self.session.send_realtime_input(
                    audio=types.Blob(data=msg["data"], mime_type="audio/pcm;rate=16000"))
            elif msg.get("mime_type") == "image/jpeg":
                frame = msg["data"]
                if isinstance(frame, str):
                    frame = base64.b64decode(frame)
                await self.session.send_realtime_input(
                    video=types.Blob(data=frame, mime_type="image/jpeg"))

    async def listen_audio(self):
        try:
            mic_info = pya.get_default_input_device_info()
        except (OSError, IOError) as exc:
            if self.on_live_status:
                self.on_live_status({"state": "audio_error", "model": MODEL, "message": "Microphone unavailable. Select a working input device in SPARK Settings."})
            return

        # Resolve Input Device by Name if provided
        resolved_input_device_index = None
        
        if self.input_device_name:
            print(f"[ADA] Attempting to find input device matching: '{self.input_device_name}'")
            count = pya.get_device_count()
            best_match = None
            
            for i in range(count):
                try:
                    info = pya.get_device_info_by_index(i)
                    if info['maxInputChannels'] > 0:
                        name = info.get('name', '')
                        # Simple case-insensitive check
                        if self.input_device_name.lower() in name.lower() or name.lower() in self.input_device_name.lower():
                             print(f"   Candidate {i}: {name}")
                             # Prioritize exact match or very close match if possible, but first match is okay for now
                             resolved_input_device_index = i
                             best_match = name
                             break
                except Exception:
                    continue
            
            if resolved_input_device_index is not None:
                print(f"[ADA] Resolved input device '{self.input_device_name}' to index {resolved_input_device_index} ({best_match})")
            else:
                print(f"[ADA] Could not find device matching '{self.input_device_name}'. Checking index...")

        # Fallback to index if Name lookup failed or wasn't provided
        if resolved_input_device_index is None and self.input_device_index is not None:
             try:
                 resolved_input_device_index = int(self.input_device_index)
                 print(f"[ADA] Requesting Input Device Index: {resolved_input_device_index}")
             except ValueError:
                 print(f"[ADA] Invalid device index '{self.input_device_index}', reverting to default.")
                 resolved_input_device_index = None

        if resolved_input_device_index is None:
             print("[ADA] Using Default Input Device")

        try:
            self.audio_stream = await asyncio.to_thread(
                pya.open,
                format=FORMAT,
                channels=CHANNELS,
                rate=SEND_SAMPLE_RATE,
                input=True,
                input_device_index=resolved_input_device_index if resolved_input_device_index is not None else mic_info["index"],
                frames_per_buffer=CHUNK_SIZE,
            )
        except OSError as e:
            print(f"[ADA] [ERR] Failed to open audio input stream: {e}")
            print("[ADA] [WARN] Audio features will be disabled. Please check microphone permissions.")
            return

        if __debug__:
            kwargs = {"exception_on_overflow": False}
        else:
            kwargs = {}
        
        # VAD Constants
        VAD_THRESHOLD = 800 # Adj based on mic sensitivity (800 is conservative for 16-bit)
        SILENCE_DURATION = 0.5 # Seconds of silence to consider "done speaking"
        
        while True:
            if self.paused:
                await asyncio.sleep(0.1)
                continue

            try:
                data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)

                # Keep draining Windows microphone capture so stale speaker
                # audio cannot be replayed after the assistant finishes.
                if self.echo_gate.mic_blocked():
                    self._is_speaking = False
                    self._silence_start_time = None
                    continue

                # 1. Send Audio
                if self.out_queue:
                    await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})
                
                # 2. VAD Logic for Video
                # rms = audioop.rms(data, 2)
                # Replacement for audioop.rms(data, 2)
                count = len(data) // 2
                if count > 0:
                    shorts = struct.unpack(f"<{count}h", data)
                    sum_squares = sum(s**2 for s in shorts)
                    rms = int(math.sqrt(sum_squares / count))
                else:
                    rms = 0
                
                if rms > VAD_THRESHOLD:
                    # Speech Detected
                    self._silence_start_time = None
                    
                    if not self._is_speaking:
                        # NEW Speech Utterance Started
                        self._is_speaking = True
                        print(f"[ADA DEBUG] [VAD] Speech Detected (RMS: {rms}). Sending Video Frame.")
                        
                        # Send ONE frame
                        if self._latest_image_payload and self.out_queue:
                            await self.out_queue.put(self._latest_image_payload)
                        else:
                            print(f"[ADA DEBUG] [VAD] No video frame available to send.")
                            
                else:
                    # Silence
                    if self._is_speaking:
                        if self._silence_start_time is None:
                            self._silence_start_time = time.time()
                        
                        elif time.time() - self._silence_start_time > SILENCE_DURATION:
                            # Silence confirmed, reset state
                            print(f"[ADA DEBUG] [VAD] Silence detected. Resetting speech state.")
                            self._is_speaking = False
                            self._silence_start_time = None

            except Exception as e:
                print(f"Error reading audio: {e}")
                await asyncio.sleep(0.1)

    async def handle_cad_request(self, prompt):
        print(f"[ADA DEBUG] [CAD] Background Task Started: handle_cad_request('{prompt}')")
        if self.on_cad_status:
            self.on_cad_status("generating")
            
        # Auto-create project if stuck in temp
        if self.project_manager.current_project == "temp":
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            new_project_name = f"Project_{timestamp}"
            print(f"[ADA DEBUG] [CAD] Auto-creating project: {new_project_name}")
            
            success, msg = self.project_manager.create_project(new_project_name)
            if success:
                self.project_manager.switch_project(new_project_name)
                # Notify User (Optional, or rely on update)
                try:
                    await self.session.send(input=f"System Notification: Automatic Project Creation. Switched to new project '{new_project_name}'.", end_of_turn=False)
                    if self.on_project_update:
                         self.on_project_update(new_project_name)
                except Exception as e:
                    print(f"[ADA DEBUG] [ERR] Failed to notify auto-project: {e}")

        # Get project cad folder path
        cad_output_dir = str(self.project_manager.get_current_project_path() / "cad")
        
        # Call the secondary agent with project path
        cad_data = await self.cad_agent.generate_prototype(prompt, output_dir=cad_output_dir)
        
        if cad_data:
            print(f"[ADA DEBUG] [OK] CadAgent returned data successfully.")
            print(f"[ADA DEBUG] [INFO] Data Check: {len(cad_data.get('vertices', []))} vertices, {len(cad_data.get('edges', []))} edges.")
            
            if self.on_cad_data:
                print(f"[ADA DEBUG] [SEND] Dispatching data to frontend callback...")
                self.on_cad_data(cad_data)
                print(f"[ADA DEBUG] [SENT] Dispatch complete.")
            
            # Save to Project
            if 'file_path' in cad_data:
                self.project_manager.save_cad_artifact(cad_data['file_path'], prompt)
            else:
                 # Fallback (legacy support)
                 self.project_manager.save_cad_artifact("output.stl", prompt)

            # Notify the model that the task is done - this triggers speech about completion
            completion_msg = "System Notification: CAD generation is complete! The 3D model is now displayed for the user. Let them know it's ready."
            try:
                await self.session.send(input=completion_msg, end_of_turn=True)
                print(f"[ADA DEBUG] [NOTE] Sent completion notification to model.")
            except Exception as e:
                 print(f"[ADA DEBUG] [ERR] Failed to send completion notification: {e}")

        else:
            print(f"[ADA DEBUG] [ERR] CadAgent returned None.")
            # Optionally notify failure
            try:
                await self.session.send(input="System Notification: CAD generation failed.", end_of_turn=True)
            except Exception:
                pass



    async def handle_write_file(self, path, content):
        print(f"[ADA DEBUG] [FS] Writing file: '{path}'")
        
        # Auto-create project if stuck in temp
        if self.project_manager.current_project == "temp":
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            new_project_name = f"Project_{timestamp}"
            print(f"[ADA DEBUG] [FS] Auto-creating project: {new_project_name}")
            
            success, msg = self.project_manager.create_project(new_project_name)
            if success:
                self.project_manager.switch_project(new_project_name)
                # Notify User
                try:
                    await self.session.send(input=f"System Notification: Automatic Project Creation. Switched to new project '{new_project_name}'.", end_of_turn=False)
                    if self.on_project_update:
                         self.on_project_update(new_project_name)
                except Exception as e:
                    print(f"[ADA DEBUG] [ERR] Failed to notify auto-project: {e}")
        
        # Force path to be relative to current project
        # If absolute path is provided, we try to strip it or just ignore it and use basename
        filename = os.path.basename(path)
        
        # If path contained subdirectories (e.g. "backend/server.py"), preserving that structure might be desired IF it's within the project.
        # But for safety, and per user request to "always create the file in the project", 
        # we will root it in the current project path.
        
        current_project_path = self.project_manager.get_current_project_path()
        final_path = current_project_path / filename # Simple flat structure for now, or allow relative?
        
        # If the user specifically wanted a subfolder, they might have provided "sub/file.txt".
        # Let's support relative paths if they don't start with /
        if not os.path.isabs(path):
             final_path = current_project_path / path
        
        print(f"[ADA DEBUG] [FS] Resolved path: '{final_path}'")

        try:
            # Ensure parent exists
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            with open(final_path, 'w', encoding='utf-8') as f:
                f.write(content)
            result = f"File '{final_path.name}' written successfully to project '{self.project_manager.current_project}'."
        except Exception as e:
            result = f"Failed to write file '{path}': {str(e)}"

        print(f"[ADA DEBUG] [FS] Result: {result}")
        try:
             await self.session.send(input=f"System Notification: {result}", end_of_turn=True)
        except Exception as e:
             print(f"[ADA DEBUG] [ERR] Failed to send fs result: {e}")

    async def handle_read_directory(self, path):
        print(f"[ADA DEBUG] [FS] Reading directory: '{path}'")
        try:
            if not os.path.exists(path):
                result = f"Directory '{path}' does not exist."
            else:
                items = os.listdir(path)
                result = f"Contents of '{path}': {', '.join(items)}"
        except Exception as e:
            result = f"Failed to read directory '{path}': {str(e)}"

        print(f"[ADA DEBUG] [FS] Result: {result}")
        try:
             await self.session.send(input=f"System Notification: {result}", end_of_turn=True)
        except Exception as e:
             print(f"[ADA DEBUG] [ERR] Failed to send fs result: {e}")

    async def handle_read_file(self, path):
        print(f"[ADA DEBUG] [FS] Reading file: '{path}'")
        try:
            if not os.path.exists(path):
                result = f"File '{path}' does not exist."
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                result = f"Content of '{path}':\n{content}"
        except Exception as e:
            result = f"Failed to read file '{path}': {str(e)}"

        print(f"[ADA DEBUG] [FS] Result: {result}")
        try:
             await self.session.send(input=f"System Notification: {result}", end_of_turn=True)
        except Exception as e:
             print(f"[ADA DEBUG] [ERR] Failed to send fs result: {e}")

    async def handle_web_agent_request(self, prompt):
        print(f"[ADA DEBUG] [WEB] Web Agent Task: '{prompt}'")
        
        async def update_frontend(image_b64, log_text):
            if self.on_web_data:
                 self.on_web_data({"image": image_b64, "log": log_text})
                 
        # Run the web agent and wait for it to return
        result = await self.web_agent.run_task(prompt, update_callback=update_frontend)
        print(f"[ADA DEBUG] [WEB] Web Agent Task Returned: {result}")
        
        # Send the final result back to the main model
        try:
             await self.session.send(input=f"System Notification: Web Agent has finished.\nResult: {result}", end_of_turn=True)
        except Exception as e:
             print(f"[ADA DEBUG] [ERR] Failed to send web agent result to model: {e}")

    async def receive_audio(self):
        "Background task to reads from the websocket and write pcm chunks to the output queue"
        try:
            while True:
                turn = self.session.receive()
                async for response in turn:
                    # 1. Handle Audio Data
                    if data := response.data:
                        if self.browser_audio:
                            # Binary PCM goes to Chromium playback, which also
                            # supplies the acoustic echo cancellation reference.
                            if self.on_audio_data:
                                self.on_audio_data(data)
                            if self.on_browser_audio:
                                self.on_browser_audio(data)
                        else:
                            first_output = self.echo_gate.on_output_received()
                            if first_output and self.echo_gate.require_rearm and self.on_mic_safety:
                                self.on_mic_safety({
                                    "muted": True, "reason": "await_user_rearm",
                                    "message": "SPARK is speaking. Tap the microphone after the reply to ask another question."
                                })
                            self.audio_in_queue.put_nowait(data)
                        # NOTE: 'continue' removed here to allow processing transcription/tools in same packet

                    # 2. Handle grounded Google Search source citations.
                    # This comes from the provider's typed grounding metadata,
                    # NOT model-generated spoken claims or untrusted HTML.
                    if response.server_content:
                        metadata = getattr(response.server_content, "grounding_metadata", None)
                        if metadata and self.on_web_sources:
                            sources = extract_grounding_sources(metadata)
                            signature = tuple(x["url"] for x in sources)
                            if sources and signature != self._grounding_signature:
                                self._grounding_signature = signature
                                self.on_web_sources({"sources": sources})
                        if getattr(response.server_content, "turn_complete", False):
                            self._grounding_signature = None
                            # Deterministic Graphify/Graphiti/Obsidian routing, off
                            # the receive loop so a slow query never blocks streaming.
                            if (self._user_utterance and not self._graphify_dispatched
                                    and (self.on_graphify_query is not None
                                         or self.on_graphiti_query is not None
                                         or self.on_obsidian_search is not None)):
                                asyncio.create_task(
                                    self.maybe_dispatch_graphify(self.session))

                    # 3. Handle Transcription (User & Model)
                    if response.server_content:
                        if response.server_content.input_transcription:
                            transcript = response.server_content.input_transcription.text
                            if transcript:
                                # Skip if this is an exact duplicate event
                                if transcript != self._last_input_transcription:
                                    # Calculate delta (Gemini may send cumulative or chunk-based text)
                                    delta = transcript
                                    if transcript.startswith(self._last_input_transcription):
                                        delta = transcript[len(self._last_input_transcription):]
                                    self._last_input_transcription = transcript
                                    
                                    # Only send if there's new text
                                    if delta:
                                        # User is speaking, so interrupt model playback!
                                        self.clear_audio_queue()

                                        # Send to frontend (Streaming)
                                        if self.on_transcription:
                                             self.on_transcription({"sender": "User", "text": delta})
                                        
                                        # Buffer for Logging
                                        if self.chat_buffer["sender"] != "User":
                                            # Flush previous if exists
                                            if self.chat_buffer["sender"] and self.chat_buffer["text"].strip():
                                                self.project_manager.log_chat(self.chat_buffer["sender"], self.chat_buffer["text"])
                                            # Start new
                                            self.chat_buffer = {"sender": "User", "text": delta}
                                            self._user_utterance = delta
                                            self._graphify_dispatched = False
                                            self._graphify_tool_used = False
                                            self._graphiti_dispatched = False
                                        else:
                                            # Append
                                            self.chat_buffer["text"] += delta
                                            self._user_utterance += delta
                        
                        if response.server_content.output_transcription:
                            transcript = response.server_content.output_transcription.text
                            if transcript:
                                # Skip if this is an exact duplicate event
                                if transcript != self._last_output_transcription:
                                    # Calculate delta (Gemini may send cumulative or chunk-based text)
                                    delta = transcript
                                    if transcript.startswith(self._last_output_transcription):
                                        delta = transcript[len(self._last_output_transcription):]
                                    self._last_output_transcription = transcript
                                    
                                    # Only send if there's new text
                                    if delta:
                                        # Send to frontend (Streaming)
                                        if self.on_transcription:
                                             self.on_transcription({"sender": "ADA", "text": delta})
                                        
                                        # Buffer for Logging
                                        if self.chat_buffer["sender"] != "ADA":
                                            # Flush previous
                                            if self.chat_buffer["sender"] and self.chat_buffer["text"].strip():
                                                self.project_manager.log_chat(self.chat_buffer["sender"], self.chat_buffer["text"])
                                            # Start new
                                            self.chat_buffer = {"sender": "ADA", "text": delta}
                                        else:
                                            # Append
                                            self.chat_buffer["text"] += delta
                        
                        # Flush buffer on turn completion if needed, 
                        # but usually better to wait for sender switch or explicit end.
                        # We can also check turn_complete signal if available in response.server_content.model_turn etc

                    # 3. Handle Tool Calls
                    if response.tool_call:
                        print("[SPARK] Gemini requested: " + ", ".join(str(getattr(fc, "name", "unknown")) for fc in (response.tool_call.function_calls or [])))
                        function_responses = []
                        for fc in response.tool_call.function_calls:
                            if fc.name == 'ask_vaos_jarvis':
                                result = (await self.jarvis_access.ask((fc.args or {}).get('question'))
                                          if self.jarvis_access else {'ok': False, 'message': 'Jarvis connection unavailable.'})
                                function_responses.append(types.FunctionResponse(
                                    id=fc.id, name=fc.name, response=result))
                                continue
                            if fc.name == 'pc_action':
                                result = (await asyncio.to_thread(self.pc_access.execute, dict(fc.args or {}))
                                          if self.pc_access else {'ok': False, 'error': 'PC autonomy unavailable.'})
                                function_responses.append(types.FunctionResponse(
                                    id=fc.id, name=fc.name, response=result))
                                continue
                            # Enforce the configured provider tool boundary on
                            # execution; never trust a model-provided name.
                            if not allowed_live_tool(live_profile(), fc.name):
                                function_responses.append(types.FunctionResponse(
                                    id=fc.id, name=fc.name,
                                    response={"result": "Tool unavailable in the current SPARK voice profile."}
                                ))
                                continue

                            if fc.name in MCP_VOICE_TOOLS:
                                if fc.name == "query_spark_graph":
                                    # Suppresses the deterministic fallback for
                                    # this turn: the tool response is authoritative.
                                    self._graphify_tool_used = True
                                answer = await self.answer_mcp_tool(fc.name, fc.args)
                                function_responses.append(types.FunctionResponse(
                                    id=fc.id, name=fc.name,
                                    response={"result": answer}
                                ))
                                continue
                            if fc.name == "get_system_status":
                                function_responses.append(types.FunctionResponse(
                                    id=fc.id, name=fc.name,
                                    response={"result": get_system_status()}
                                ))
                                continue
                            if fc.name in ["generate_cad", "run_web_agent", "write_file", "read_directory", "read_file", "create_project", "switch_project", "list_projects", "list_smart_devices", "control_light", "discover_printers", "print_stl", "get_print_status", "iterate_cad", "launch_desktop_app"]:
                                prompt = fc.args.get("prompt", "") # Prompt is not present for all tools
                                
                                # Check Permissions (Default to True if not set)
                                confirmation_required = tool_confirmation_required(fc.name, self.permissions)
                                
                                if not confirmation_required:
                                    print(f"[ADA DEBUG] [TOOL] Permission check: '{fc.name}' -> AUTO-ALLOW")
                                    # Skip confirmation block and jump to execution
                                    pass
                                else:
                                    # Confirmation Logic
                                    if not self.on_tool_confirmation:
                                        function_responses.append(types.FunctionResponse(
                                            id=fc.id, name=fc.name,
                                            response={"result": "Tool denied: interactive confirmation unavailable."}
                                        ))
                                        continue
                                    if self.on_tool_confirmation:
                                        import uuid
                                        request_id = str(uuid.uuid4())
                                    print(f"[ADA DEBUG] [STOP] Requesting confirmation for '{fc.name}' (ID: {request_id})")
                                    
                                    future = asyncio.Future()
                                    self._pending_confirmations[request_id] = future
                                    
                                    self.on_tool_confirmation({
                                        "id": request_id, 
                                        "tool": fc.name, 
                                        "args": fc.args
                                    })
                                    
                                    try:
                                        # A missing/abandoned confirmation can
                                        # never stall hands-free conversation indefinitely.
                                        confirmed = bool(await asyncio.wait_for(future, timeout=45))
                                    except asyncio.TimeoutError:
                                        confirmed = False
                                        print("[SPARK] Tool approval timed out; action denied.")
                                    finally:
                                        self._pending_confirmations.pop(request_id, None)

                                    print(f"[ADA DEBUG] [CONFIRM] Request {request_id} resolved. Confirmed: {confirmed}")

                                    if not confirmed:
                                        print(f"[ADA DEBUG] [DENY] Tool call '{fc.name}' denied by user.")
                                        function_response = types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response={
                                                "result": "User denied the request to use this tool.",
                                            }
                                        )
                                        function_responses.append(function_response)
                                        continue

                                    if not confirmed:
                                        print(f"[ADA DEBUG] [DENY] Tool call '{fc.name}' denied by user.")
                                        function_response = types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response={
                                                "result": "User denied the request to use this tool.",
                                            }
                                        )
                                        function_responses.append(function_response)
                                        continue

                                # Launching desktop apps must never auto-allow, including when
                                # client confirmation handler is unavailable.
                                if fc.name == "launch_desktop_app":
                                    if not self.on_tool_confirmation:
                                        function_responses.append(types.FunctionResponse(
                                            id=fc.id, name=fc.name,
                                            response={"result": "Desktop launch unavailable without interactive user confirmation."}
                                        ))
                                        continue
                                    result = await asyncio.to_thread(
                                        launch_allowed_app, fc.args.get("app", ""))
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name,
                                        response={"result": result["message"]}
                                    ))
                                    continue

                                # If confirmed (or no callback configured, or auto-allowed), proceed
                                if fc.name == "generate_cad":
                                    print(f"\n[ADA DEBUG] --------------------------------------------------")
                                    print(f"[ADA DEBUG] [TOOL] Tool Call Detected: 'generate_cad'")
                                    print(f"[ADA DEBUG] [IN] Arguments: prompt='{prompt}'")
                                    
                                    asyncio.create_task(self.handle_cad_request(prompt))
                                    # No function response needed - model already acknowledged when user asked
                                
                                elif fc.name == "run_web_agent":
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'run_web_agent' with prompt='{prompt}'")
                                    asyncio.create_task(self.handle_web_agent_request(prompt))
                                    
                                    result_text = "Web Navigation started. Do not reply to this message."
                                    function_response = types.FunctionResponse(
                                        id=fc.id,
                                        name=fc.name,
                                        response={
                                            "result": result_text,
                                        }
                                    )
                                    print(f"[ADA DEBUG] [RESPONSE] Sending function response: {function_response}")
                                    function_responses.append(function_response)



                                elif fc.name == "write_file":
                                    path = fc.args["path"]
                                    content = fc.args["content"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'write_file' path='{path}'")
                                    asyncio.create_task(self.handle_write_file(path, content))
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": "Writing file..."}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "read_directory":
                                    path = fc.args["path"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'read_directory' path='{path}'")
                                    asyncio.create_task(self.handle_read_directory(path))
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": "Reading directory..."}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "read_file":
                                    path = fc.args["path"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'read_file' path='{path}'")
                                    asyncio.create_task(self.handle_read_file(path))
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": "Reading file..."}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "create_project":
                                    name = fc.args["name"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'create_project' name='{name}'")
                                    success, msg = self.project_manager.create_project(name)
                                    if success:
                                        # Auto-switch to the newly created project
                                        self.project_manager.switch_project(name)
                                        msg += f" Switched to '{name}'."
                                        if self.on_project_update:
                                            self.on_project_update(name)
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": msg}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "switch_project":
                                    name = fc.args["name"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'switch_project' name='{name}'")
                                    success, msg = self.project_manager.switch_project(name)
                                    if success:
                                        if self.on_project_update:
                                            self.on_project_update(name)
                                        # Gather project context and send to AI (silently, no response expected)
                                        context = self.project_manager.get_project_context()
                                        print(f"[ADA DEBUG] [PROJECT] Sending project context to AI ({len(context)} chars)")
                                        try:
                                            await self.session.send(input=f"System Notification: {msg}\n\n{context}", end_of_turn=False)
                                        except Exception as e:
                                            print(f"[ADA DEBUG] [ERR] Failed to send project context: {e}")
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": msg}
                                    )
                                    function_responses.append(function_response)
                                
                                elif fc.name == "list_projects":
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'list_projects'")
                                    projects = self.project_manager.list_projects()
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": f"Available projects: {', '.join(projects)}"}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "list_smart_devices":
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'list_smart_devices'")
                                    # Use cached devices directly for speed
                                    # devices_dict is {ip: SmartDevice}
                                    
                                    dev_summaries = []
                                    frontend_list = []
                                    
                                    for ip, d in self.kasa_agent.devices.items():
                                        dev_type = "unknown"
                                        if d.is_bulb: dev_type = "bulb"
                                        elif d.is_plug: dev_type = "plug"
                                        elif d.is_strip: dev_type = "strip"
                                        elif d.is_dimmer: dev_type = "dimmer"
                                        
                                        # Format for Model
                                        info = f"{d.alias} (IP: {ip}, Type: {dev_type})"
                                        if d.is_on:
                                            info += " [ON]"
                                        else:
                                            info += " [OFF]"
                                        dev_summaries.append(info)
                                        
                                        # Format for Frontend
                                        frontend_list.append({
                                            "ip": ip,
                                            "alias": d.alias,
                                            "model": d.model,
                                            "type": dev_type,
                                            "is_on": d.is_on,
                                            "brightness": d.brightness if d.is_bulb or d.is_dimmer else None,
                                            "hsv": d.hsv if d.is_bulb and d.is_color else None,
                                            "has_color": d.is_color if d.is_bulb else False,
                                            "has_brightness": d.is_dimmable if d.is_bulb or d.is_dimmer else False
                                        })
                                    
                                    result_str = "No devices found in cache."
                                    if dev_summaries:
                                        result_str = "Found Devices (Cached):\n" + "\n".join(dev_summaries)
                                    
                                    # Trigger frontend update
                                    if self.on_device_update:
                                        self.on_device_update(frontend_list)

                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "control_light":
                                    target = fc.args["target"]
                                    action = fc.args["action"]
                                    brightness = fc.args.get("brightness")
                                    color = fc.args.get("color")
                                    
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'control_light' Target='{target}' Action='{action}'")
                                    
                                    result_msg = f"Action '{action}' on '{target}' failed."
                                    success = False
                                    
                                    if action == "turn_on":
                                        success = await self.kasa_agent.turn_on(target)
                                        if success:
                                            result_msg = f"Turned ON '{target}'."
                                    elif action == "turn_off":
                                        success = await self.kasa_agent.turn_off(target)
                                        if success:
                                            result_msg = f"Turned OFF '{target}'."
                                    elif action == "set":
                                        success = True
                                        result_msg = f"Updated '{target}':"
                                    
                                    # Apply extra attributes if 'set' or if we just turned it on and want to set them too
                                    if success or action == "set":
                                        if brightness is not None:
                                            sb = await self.kasa_agent.set_brightness(target, brightness)
                                            if sb:
                                                result_msg += f" Set brightness to {brightness}."
                                        if color is not None:
                                            sc = await self.kasa_agent.set_color(target, color)
                                            if sc:
                                                result_msg += f" Set color to {color}."

                                    # Notify Frontend of State Change
                                    if success:
                                        # We don't need full discovery, just refresh known state or push update
                                        # But for simplicity, let's get the standard list representation
                                        # KasaAgent updates its internal state on control, so we can rebuild the list
                                        
                                        # Quick rebuild of list from internal dict
                                        updated_list = []
                                        for ip, dev in self.kasa_agent.devices.items():
                                            # We need to ensure we have the correct dict structure expected by frontend
                                            # We duplicate logic from KasaAgent.discover_devices a bit, but that's okay for now or we can add a helper
                                            # Ideally KasaAgent has a 'get_devices_list()' method.
                                            # Use the cached objects in self.kasa_agent.devices
                                            
                                            dev_type = "unknown"
                                            if dev.is_bulb: dev_type = "bulb"
                                            elif dev.is_plug: dev_type = "plug"
                                            elif dev.is_strip: dev_type = "strip"
                                            elif dev.is_dimmer: dev_type = "dimmer"

                                            d_info = {
                                                "ip": ip,
                                                "alias": dev.alias,
                                                "model": dev.model,
                                                "type": dev_type,
                                                "is_on": dev.is_on,
                                                "brightness": dev.brightness if dev.is_bulb or dev.is_dimmer else None,
                                                "hsv": dev.hsv if dev.is_bulb and dev.is_color else None,
                                                "has_color": dev.is_color if dev.is_bulb else False,
                                                "has_brightness": dev.is_dimmable if dev.is_bulb or dev.is_dimmer else False
                                            }
                                            updated_list.append(d_info)
                                            
                                        if self.on_device_update:
                                            self.on_device_update(updated_list)
                                    else:
                                        # Report Error
                                        if self.on_error:
                                            self.on_error(result_msg)

                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_msg}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "discover_printers":
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'discover_printers'")
                                    printers = await self.printer_agent.discover_printers()
                                    # Format for model
                                    if printers:
                                        printer_list = []
                                        for p in printers:
                                            printer_list.append(f"{p['name']} ({p['host']}:{p['port']}, type: {p['printer_type']})")
                                        result_str = "Found Printers:\n" + "\n".join(printer_list)
                                    else:
                                        result_str = "No printers found on network. Ensure printers are on and running OctoPrint/Moonraker."
                                    
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "print_stl":
                                    stl_path = fc.args["stl_path"]
                                    printer = fc.args["printer"]
                                    profile = fc.args.get("profile")
                                    
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'print_stl' STL='{stl_path}' Printer='{printer}'")
                                    
                                    # Resolve 'current' to project STL
                                    if stl_path.lower() == "current":
                                        stl_path = "output.stl" # Let printer agent resolve it in root_path

                                    # Get current project path
                                    project_path = str(self.project_manager.get_current_project_path())
                                    
                                    result = await self.printer_agent.print_stl(
                                        stl_path, 
                                        printer, 
                                        profile, 
                                        root_path=project_path
                                    )
                                    result_str = result.get("message", "Unknown result")
                                    
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "get_print_status":
                                    printer = fc.args["printer"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'get_print_status' Printer='{printer}'")
                                    
                                    status = await self.printer_agent.get_print_status(printer)
                                    if status:
                                        result_str = f"Printer: {status.printer}\n"
                                        result_str += f"State: {status.state}\n"
                                        result_str += f"Progress: {status.progress_percent:.1f}%\n"
                                        if status.time_remaining:
                                            result_str += f"Time Remaining: {status.time_remaining}\n"
                                        if status.time_elapsed:
                                            result_str += f"Time Elapsed: {status.time_elapsed}\n"
                                        if status.filename:
                                            result_str += f"File: {status.filename}\n"
                                        if status.temperatures:
                                            temps = status.temperatures
                                            if "hotend" in temps:
                                                result_str += f"Hotend: {temps['hotend']['current']:.0f}Â°C / {temps['hotend']['target']:.0f}Â°C\n"
                                            if "bed" in temps:
                                                result_str += f"Bed: {temps['bed']['current']:.0f}Â°C / {temps['bed']['target']:.0f}Â°C"
                                    else:
                                        result_str = f"Could not get status for printer '{printer}'. Ensure it is discovered first."
                                    
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "iterate_cad":
                                    prompt = fc.args["prompt"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'iterate_cad' Prompt='{prompt}'")
                                    
                                    # Emit status
                                    if self.on_cad_status:
                                        self.on_cad_status("generating")
                                    
                                    # Get project cad folder path
                                    cad_output_dir = str(self.project_manager.get_current_project_path() / "cad")
                                    
                                    # Call CadAgent to iterate on the design
                                    cad_data = await self.cad_agent.iterate_prototype(prompt, output_dir=cad_output_dir)
                                    
                                    if cad_data:
                                        print(f"[ADA DEBUG] [OK] CadAgent iteration returned data successfully.")
                                        
                                        # Dispatch to frontend
                                        if self.on_cad_data:
                                            print(f"[ADA DEBUG] [SEND] Dispatching iterated CAD data to frontend...")
                                            self.on_cad_data(cad_data)
                                            print(f"[ADA DEBUG] [SENT] Dispatch complete.")
                                        
                                        # Save to Project
                                        self.project_manager.save_cad_artifact("output.stl", f"Iteration: {prompt}")
                                        
                                        result_str = f"Successfully iterated design: {prompt}. The updated 3D model is now displayed."
                                    else:
                                        print(f"[ADA DEBUG] [ERR] CadAgent iteration returned None.")
                                        result_str = f"Failed to iterate design with prompt: {prompt}"
                                    
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    )
                                    function_responses.append(function_response)
                        if function_responses:
                            await self.session.send_tool_response(function_responses=function_responses)
                
                # The model turn has ended; release mic only after local
                # output playback drains, plus a short acoustic cooldown.
                if not self.browser_audio:
                    self.echo_gate.on_turn_finished(
                        queue_empty=self.audio_in_queue.empty())
                # Preserve already-received PCM after a turn finishes: the speaker
                # consumer may still be playing its queued chunks. Only the explicit
                # interruption path (clear_audio_queue) may discard playback audio.
                self.flush_chat()
        except Exception as e:
            print(f"Error in receive_audio: {e}")
            traceback.print_exc()
            # CRITICAL: Re-raise to crash the TaskGroup and trigger outer loop reconnect
            raise e

    async def play_audio(self):
        try:
            stream = await asyncio.to_thread(
                pya.open,
                format=FORMAT,
                channels=CHANNELS,
                rate=RECEIVE_SAMPLE_RATE,
                output=True,
                output_device_index=self.output_device_index,
            )
        except (OSError, IOError):
            if self.on_live_status:
                self.on_live_status({"state": "audio_error", "model": MODEL,
                    "message": "Speaker unavailable. Select a working output device in Windows."})
            return
        while True:
            bytestream = await self.audio_in_queue.get()
            # Mark speaker active before producing any physical output.
            self.echo_gate.on_playback_started()
            try:
                if self.on_audio_data:
                    self.on_audio_data(bytestream)
                await asyncio.to_thread(stream.write, bytestream)
            finally:
                self.echo_gate.on_playback_finished(
                    queue_empty=self.audio_in_queue.empty())

    async def get_frames(self):
        cap = await asyncio.to_thread(cv2.VideoCapture, 0, cv2.CAP_AVFOUNDATION)
        while True:
            if self.paused:
                await asyncio.sleep(0.1)
                continue
            frame = await asyncio.to_thread(self._get_frame, cap)
            if frame is None:
                break
            await asyncio.sleep(1.0)
            if self.out_queue:
                await self.out_queue.put(frame)
        cap.release()

    def _get_frame(self, cap):
        ret, frame = cap.read()
        if not ret:
            return None
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(frame_rgb)
        img.thumbnail([1024, 1024])
        image_io = io.BytesIO()
        img.save(image_io, format="jpeg")
        image_io.seek(0)
        image_bytes = image_io.read()
        return {"mime_type": "image/jpeg", "data": base64.b64encode(image_bytes).decode()}

    async def _get_screen(self):
        pass 
    async def get_screen(self):
         pass

    async def run(self, start_message=None):
        if client is None:
            raise RuntimeError("Gemini Live is not configured. Set GEMINI_API_KEY privately in backend/.env.")
        retry_delay = 1
        reconnect_attempts = 0
        is_reconnect = False
        
        while not self.stop_event.is_set():
            try:
                if self.on_live_status:
                    self.on_live_status({"state": "connecting", "model": MODEL, "message": "Connecting to Gemini Live..."})
                print(f"[SPARK] Connecting to Gemini Live model {MODEL}; profile={live_profile()}...")
                async with (
                    client.aio.live.connect(model=MODEL, config=jarvis_live_config(pc_live_config(
                        config, bool(self.pc_access and self.pc_access.enabled())),
                        bool(self.jarvis_access and self.jarvis_access.enabled()))) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session = session
                    # Reconnection must not reopen a microphone which the
                    # cinematic reply had latched closed.
                    self.echo_gate.reset(
                        hold_for_rearm=(is_reconnect and self.echo_gate.require_rearm
                                        and not self.browser_audio))
                    if is_reconnect and self.echo_gate.require_rearm and not self.browser_audio and self.on_mic_safety:
                        self.on_mic_safety({
                            "muted": True, "reason": "await_user_rearm",
                            "message": "SPARK reconnected. Activate the microphone to resume."
                        })
                    if self.on_live_status:
                        self.on_live_status({"state": "connected", "model": MODEL, "message": "SPARK Core connected to Gemini Live."})

                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue = asyncio.Queue(maxsize=10)

                    tg.create_task(self.send_realtime())
                    if not self.browser_audio:
                        tg.create_task(self.listen_audio())
                    # tg.create_task(self._process_video_queue()) # Removed in favor of VAD

                    if self.video_mode == "camera":
                        tg.create_task(self.get_frames())
                    elif self.video_mode == "screen":
                        tg.create_task(self.get_screen())

                    tg.create_task(self.receive_audio())
                    if not self.browser_audio:
                        tg.create_task(self.play_audio())

                    # Handle Startup vs Reconnect Logic
                    if not is_reconnect:
                        if start_message:
                            print(f"[ADA DEBUG] [INFO] Sending start message: {start_message}")
                            await self.session.send_client_content(turns={"role": "user", "parts": [{"text": start_message}]}, turn_complete=True)
                        
                        # Sync Project State
                        if self.on_project_update and self.project_manager:
                            self.on_project_update(self.project_manager.current_project)
                    
                    else:
                        # A transport reconnect must NEVER initiate a new
                        # unsolicited spoken turn. Earlier code injected a
                        # "please acknowledge" history prompt on every retry.
                        print("[SPARK] Live reconnect is silent; awaiting user input.")

                    # Reset retry delay on successful connection
                    retry_delay = 1
                    
                    # Wait until stop event, or until the session task group exits (which happens on error)
                    # Actually, the TaskGroup context manager will exit if any tasks fail/cancel.
                    # We need to keep this block alive.
                    # The original code just waited on stop_event, but that doesn't account for session death.
                    # We should rely on the TaskGroup raising an exception when subtasks fail (like receive_audio).
                    
                    # However, since receive_audio is a task in the group, if it crashes (connection closed), 
                    # the group will cancel others and exit. We catch that exit below.
                    
                    # We can await stop_event, but if the connection dies, receive_audio crashes -> group closes -> we exit `async with` -> restart loop.
                    # To ensure we don't block indefinitely if connection dies silently (unlikely with receive_audio), we just wait.
                    await self.stop_event.wait()

            except asyncio.CancelledError:
                print(f"[ADA DEBUG] [STOP] Main loop cancelled.")
                break
                
            except Exception as e:
                # This catches the ExceptionGroup from TaskGroup or direct exceptions
                message = live_error_message(e)
                print(f"[SPARK] {message}")
                if self.on_live_status:
                    self.on_live_status({"state": "error", "model": MODEL, "message": message})
                if live_error_requires_user_action(e):
                    break  # Never spin/retry an unavailable model, bad key or depleted quota.
                if self.stop_event.is_set():
                    break
                if reconnect_attempts >= 1:
                    break
                reconnect_attempts += 1
                
                print(f"[ADA DEBUG] [RETRY] Reconnecting in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 10) # Exponential backoff capped at 10s
                is_reconnect = True # Next loop will be a reconnect
                
            finally:
                self.session = None
                # Cleanup before retry
                if hasattr(self, 'audio_stream') and self.audio_stream:
                    try:
                        self.audio_stream.close()
                    except: 
                        pass

def get_input_devices():
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    devices = []
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
            devices.append((i, p.get_device_info_by_host_api_device_index(0, i).get('name')))
    p.terminate()
    return devices

def get_output_devices():
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    devices = []
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxOutputChannels')) > 0:
            devices.append((i, p.get_device_info_by_host_api_device_index(0, i).get('name')))
    p.terminate()
    return devices

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        type=str,
        default=DEFAULT_MODE,
        help="pixels to stream from",
        choices=["camera", "screen", "none"],
    )
    args = parser.parse_args()
    main = AudioLoop(video_mode=args.mode)
    asyncio.run(main.run())

