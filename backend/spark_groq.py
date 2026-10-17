"""Explicit cloud-only Groq fallback for SPARK. NO local Ollama runtime.

Free-tier Groq is rate limited: never auto-upgrade, bill, retry a 429,
send a Gemini request, or load unknown remotely supplied tool commands.
Keeps the existing Chromium AEC microphone/speaker bridge unchanged.
"""
import array
import asyncio
import io
import math
import os
import re
import sys
import wave

from spark_public_apis import public_api_answer

CHAT_URL="https://api.groq.com/openai/v1/chat/completions"
STT_URL="https://api.groq.com/openai/v1/audio/transcriptions"
TTS_URL="https://api.groq.com/openai/v1/audio/speech"
_ALLOWED_MODELS=frozenset(("llama-3.1-8b-instant","openai/gpt-oss-20b"))
SYSTEM_PROMPT=(
    "You are SPARK, a concise, cinematic but original aerospace-style AI assistant. "
    "Speak with composed, refined British-style diction in your wording and subtle wit. "
    "Keep replies under 150 characters, ideally one helpful sentence. "
    "You have no general internet search, file, desktop or computer-control tools. "
    "Do not invent fresh news, live sources, or claim you performed an action."
)

class GroqUnavailable(Exception):
    """Redacted user-facing status. Never include provider body or credentials."""

def cloud_provider():
    return "groq" if os.environ.get("SPARK_AI_PROVIDER","gemini").strip().lower()=="groq" else "gemini"

def groq_model():
    model=os.environ.get("SPARK_GROQ_MODEL","llama-3.1-8b-instant").strip()
    return model if model in _ALLOWED_MODELS else "llama-3.1-8b-instant"

def tts_text(reply):
    text=re.sub(r"\s+"," ",str(reply)).strip()
    # Groq Orpheus maximum is 200 characters, inclusive of directions.
    return "[professionally] "+text[:170]

def pcm_to_wav(pcm):
    if not isinstance(pcm,bytes) or len(pcm)>450000 or len(pcm)%2:
        raise ValueError("Invalid 16kHz microphone PCM length")
    out=io.BytesIO()
    with wave.open(out,"wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    return out.getvalue()

def wav_to_pcm24k(data):
    if not isinstance(data,bytes) or len(data)>2_000_000:
        raise GroqUnavailable("Groq speech response size is invalid.")
    try:
        with wave.open(io.BytesIO(data),"rb") as wav:
            channels=wav.getnchannels()
            rate=wav.getframerate()
            width=wav.getsampwidth()
            frames=wav.getnframes()
            if channels not in (1,2) or rate<8000 or rate>48000 or width!=2 or frames>480000:
                raise ValueError("Unsupported WAV format")
            samples=array.array("h")
            samples.frombytes(wav.readframes(frames))
            if sys.byteorder=="big":
                samples.byteswap()
        if channels==2:
            samples=array.array("h",((samples[2*i]+samples[2*i+1])//2 for i in range(frames)))
        target_count=round(frames*24000/rate)
        output=array.array("h")
        for n in range(target_count):
            point=n*rate/24000
            index=int(point)
            if index>=frames-1:
                value=samples[-1]
            else:
                ratio=point-index
                value=round(samples[index]*(1-ratio)+samples[index+1]*ratio)
            output.append(max(-32768,min(32767,int(value))))
        if sys.byteorder=="big":
            output.byteswap()
        return output.tobytes()
    except (EOFError,ValueError,wave.Error,IndexError,OverflowError) as exc:
        raise GroqUnavailable("Groq returned unsupported speech audio.") from None

class GroqClient:
    def __init__(self,key=None):
        self.key=key or os.environ.get("GROQ_API_KEY","")
        if not self.key:
            raise GroqUnavailable("Set GROQ_API_KEY in backend/.env for opt-in Groq voice.")

    async def _http(self,url,*,body=None,form=None,want_binary=False):
        import aiohttp
        assert url in (CHAT_URL, STT_URL,TTS_URL), "Only approved Groq endpoints"
        headers={"Authorization":"Bearer "+self.key}
        if body is not None:
            headers["Content-Type"]="application/json"
        try:
            timeout=aiohttp.ClientTimeout(total=30,connect=7)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url,json=body,data=form,headers=headers,allow_redirects=False) as response:
                    if response.status==429:
                        raise GroqUnavailable("Groq free-tier rate limit reached (429). No automatic retry or paid fallback.")
                    if response.status in (401,403):
                        raise GroqUnavailable("Groq API key rejected (401/403); check GROQ_API_KEY privately.")
                    if response.status>=300:
                        raise GroqUnavailable("Groq cloud request failed; check model availability and connection.")
                    if response.content_length and response.content_length>2_000_000:
                        raise GroqUnavailable("Groq response exceeds configured size limit.")
                    raw=await response.content.read(2_000_001)
                    if len(raw)>2_000_000:
                        raise GroqUnavailable("Groq response exceeds configured size limit.")
                    if want_binary:
                        return raw
                    import json
                    return json.loads(raw)
        except (asyncio.TimeoutError,OSError) as exc:
            raise GroqUnavailable("Groq request timed out or network unavailable.") from None

    async def transcribe(self,wav):
        if len(wav)>450100:
            raise GroqUnavailable("Voice request too long; please speak a shorter phrase.")
        import aiohttp
        form=aiohttp.FormData()
        form.add_field("file",wav,filename="speech.wav",content_type="audio/wav")
        form.add_field("model","whisper-large-v3-turbo")
        form.add_field("language","en")
        result=await self._http(STT_URL,form=form)
        if not isinstance(result,dict):
            raise GroqUnavailable("Speech recognition returned invalid content.")
        return str(result.get("text",""))[:500].strip()

    async def chat(self,prompt,history):
        messages=[{"role":"system","content":SYSTEM_PROMPT}]
        messages+=history[-6:]
        messages.append({"role":"user","content":prompt[:1200]})
        body={"model":groq_model(),"messages":messages,"stream":False,
              "temperature":0.5,"max_completion_tokens":160}
        result=await self._http(CHAT_URL,body=body)
        try:
            value=result["choices"][0]["message"]["content"]
            if not isinstance(value,str) or not value.strip():
                raise ValueError()
            return value.strip()[:700]
        except (KeyError,TypeError,IndexError,ValueError):
            raise GroqUnavailable("Groq returned no usable text response.") from None

    async def speak(self,text):
        body={"model":"canopylabs/orpheus-v1-english",
              "voice":"daniel","input":tts_text(text),"response_format":"wav"}
        return await self._http(TTS_URL,body=body,want_binary=True)

async def get_public_json(url):
    # This function is passed only URLs constructed by spark_public_apis,
    # never an arbitrary model/user URL or tool-call argument.
    import aiohttp
    if not (url.startswith("https://api.frankfurter.dev/v2/rate/") or
            url.startswith("https://en.wikipedia.org/api/rest_v1/page/summary/")):
        raise ValueError("Public API host not allowed.")
    timeout=aiohttp.ClientTimeout(total=12,connect=5)
    headers={"User-Agent":"SPARKPublicAPI/1.0 (https://github.com/vyndivybes/spark)"}
    try:
        async with aiohttp.ClientSession(timeout=timeout,headers=headers) as session:
            async with session.get(url,allow_redirects=False) as response:
                if response.status!=200:
                    raise GroqUnavailable("Public data provider is unavailable.")
                raw=await response.content.read(50001)
                if len(raw)>50000:
                    raise GroqUnavailable("Public data response too large.")
                import json
                return json.loads(raw)
    except (OSError,asyncio.TimeoutError):
        raise GroqUnavailable("Public data service is unreachable.") from None

class GroqVoiceLoop:
    provider="groq"
    browser_audio=True
    def __init__(self,api=None,on_transcription=None,on_browser_audio=None,
                 on_web_sources=None,on_live_status=None,on_error=None,
                 audio_playback_wait=True,fetch_public=None):
        self.api=api or GroqClient()
        self.on_transcription=on_transcription
        self.on_browser_audio=on_browser_audio
        self.on_web_sources=on_web_sources
        self.on_live_status=on_live_status
        self.on_error=on_error
        self.audio_playback_wait=audio_playback_wait
        self.fetch_public=fetch_public or get_public_json
        self.out_queue=asyncio.Queue(maxsize=12)
        self.stop_event=asyncio.Event()
        self.session=self
        self.browser_ready=False
        self.paused=True
        self.owner_sid=None
        self.printer_agent=None
        self._busy=False
        self._speaking=False
        self._samples=[]
        self._speech_chunks=0
        self._silence_chunks=0
        self._history=[]
        self._lock=asyncio.Lock()

    @property
    def accepting_mic(self):
        # Full-duplex Chromium AEC remains on, but stale samples captured
        # while cloud STT/TTS is running must never re-trigger another turn.
        return not (self.paused or self._busy or self._speaking or self.stop_event.is_set())

    @property
    def recorded_chunks(self):
        return len(self._samples)

    def set_paused(self,paused):
        self.paused=bool(paused)
        if self.paused:
            self._reset_vad()

    def _reset_vad(self):
        self._samples=[]
        self._speech_chunks=0
        self._silence_chunks=0

    def _drop_stale_pcm(self):
        while not self.out_queue.empty():
            try:
                self.out_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def stop(self):
        self.stop_event.set()
        self.set_paused(True)
        self.session=None

    async def run(self):
        if self.on_live_status:
            self.on_live_status({"state":"connected","model":groq_model(),
                                 "message":"Groq cloud voice configured; credentials are verified on first request."})
        pump=asyncio.create_task(self._pump())
        try:
            await self.stop_event.wait()
        finally:
            pump.cancel()
            await asyncio.gather(pump,return_exceptions=True)

    async def _pump(self):
        while not self.stop_event.is_set():
            payload=await self.out_queue.get()
            if isinstance(payload,dict) and isinstance(payload.get("data"),bytes):
                await self.process_pcm(payload["data"])

    async def process_pcm(self,pcm):
        # Chromium worklet sends exactly 100ms / 16 kHz / 16-bit mono.
        if self.paused or self._busy or self._speaking or self.stop_event.is_set():
            return
        if not isinstance(pcm,bytes) or len(pcm)!=3200:
            return
        samples=array.array("h")
        samples.frombytes(pcm)
        if sys.byteorder=="big":
            samples.byteswap()
        # Sparse RMS; inexpensive enough for low-end Windows laptops.
        rms=math.sqrt(sum(int(v)*int(v) for v in samples[::8])/200)
        voiced=rms>=650
        if not self._samples:
            if not voiced:
                return
            self._speech_chunks=0
            self._silence_chunks=0
        self._samples.append(pcm)
        if voiced:
            self._speech_chunks+=1
            self._silence_chunks=0
        else:
            self._silence_chunks+=1
        if len(self._samples)>120:
            self._reset_vad()  # bound RAM and avoid uploading very long speech
            return
        if self._silence_chunks>=8:
            frames=self._samples[:-self._silence_chunks]
            voiced_chunks=self._speech_chunks
            self._reset_vad()
            if voiced_chunks>=3 and frames:
                await self.handle_audio(pcm_to_wav(b"".join(frames)))

    async def handle_audio(self,wav):
        async with self._lock:
            self._busy=True
            try:
                phrase=await self.api.transcribe(wav)
                if not phrase:
                    return
                if self.on_transcription:
                    self.on_transcription({"sender":"User","text":phrase})
                await self._answer(phrase)
            except GroqUnavailable as error:
                if self.on_error:
                    self.on_error(str(error))
            except Exception:
                if self.on_error:
                    self.on_error("Groq voice request failed; verify the connection and free-tier limits.")
            finally:
                self._drop_stale_pcm()
                self._busy=False
                self._reset_vad()

    async def handle_text(self,prompt):
        if not isinstance(prompt,str) or not prompt.strip():
            return
        async with self._lock:
            self._busy=True
            try:
                await self._answer(prompt.strip()[:1200])
            except GroqUnavailable as error:
                if self.on_error:
                    self.on_error(str(error))
            except Exception:
                if self.on_error:
                    self.on_error("Groq request failed; check the cloud service.")
            finally:
                self._busy=False

    async def _answer(self,prompt):
        # Fixed public API query paths avoid spending inference tokens.
        data=await public_api_answer(prompt,self.fetch_public)
        if data:
            answer=data["text"]
            if data.get("sources") and self.on_web_sources:
                self.on_web_sources({"sources":data["sources"]})
        else:
            answer=await self.api.chat(prompt,list(self._history))
            self._history.extend(({"role":"user","content":prompt[:1200]},
                                  {"role":"assistant","content":answer[:700]}))
            self._history=self._history[-6:]
        if self.on_transcription:
            self.on_transcription({"sender":"ADA","text":answer})
        if not self.on_browser_audio:
            return
        # Groq Orpheus accepts up to 200 input characters, so only speak a
        # concise summary while preserving the full written answer in chat.
        self._speaking=True
        try:
            wav=await self.api.speak(answer)
            pcm=wav_to_pcm24k(wav)
            # BrowserEchoAudio accepts bounded PCM packets only. A complete
            # Orpheus WAV may be much larger than a single socket frame.
            for start in range(0,len(pcm),48000):
                self.on_browser_audio(pcm[start:start+48000])
            if self.audio_playback_wait:
                await asyncio.sleep(min(30,len(pcm)/48000+0.7))
        finally:
            self._drop_stale_pcm()
            self._speaking=False
            self._reset_vad()
