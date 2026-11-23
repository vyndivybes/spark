# SPARK personal cinematic voice — VoiceStudio local adapter

This is a **personal-use, free, separately installed local speech provider**.
SPARK does not bundle or modify VoiceStudio; it talks to the independently
running speech service over `127.0.0.1`. No subscription, API key, or external
speech endpoint is introduced. This is intended for SPARK **personal use**;
it is not an authorization to use VoiceStudio model weights in VAOS/VYNDI
commercial operations. Check the selected voice engine/model licence.

## Setup (Windows)

1. Install the **official VoiceStudio Windows release** from
   https://github.com/debpalash/VoiceStudio/releases and verify its publisher/
   checksums before installation. Avoid executing unreviewed install scripts.
2. Open VoiceStudio. Complete its local model installation and **accept the
   model licence explicitly**. Its default OmniVoice weights are
   non-commercial; this must not be silently reused by company systems.
3. Keep its local speech service running. Open
   http://127.0.0.1:3900/.well-known/voicestudio-speech in your **local**
   browser to confirm the documented speech service is reachable. Different
   ports require `SPARK_VOICESTUDIO_PORT` to be set to a numeric port.
4. In the SPARK repository PowerShell session run:

   ```powershell
   .\start-spark.ps1 -AIProvider groq -VoiceProvider voicestudio
   ```

This selects local synthesized voice for the **Groq Chromium-AEC** speech
path. It does not switch Gemini Live voice, and it does not replace SPARK's
LLM, browser or workplace permissions. A local model may use substantial
RAM/CPU (especially on an 8 GB Windows machine); initial model downloads
consume disk. No model is automatically downloaded by SPARK.

To revert without removing VoiceStudio:

```powershell
.\start-spark.ps1 -AIProvider groq -VoiceProvider windows
```

The default mode remains the existing Windows speech engine. In
VoiceStudio mode, if VoiceStudio is absent, slow or refuses a model licence,
**SPARK reports a speech failure**; it does not secretly switch back to
Windows speech or a cloud TTS provider. You can stop voice output without
authorizing another provider.

## Technical contract

- Electron main-process `spark:voicestudio:render` IPC is restricted to
  the trusted SPARK cockpit. Only `SPARK_VOICE_PROVIDER=voicestudio` enables
  the request.
- The adapter accepts *speech text only* (1–1600 characters) and makes
  a fixed POST to `http://127.0.0.1:<port>/v1/audio/speech`. The renderer
  cannot select an origin, URL path, model, file path or other HTTP method.
  The only allowed outputs are bounded WAV bytes (12 MiB max), checked
  for a WAV signature. Redirects, wrong MIME types and oversized bodies
  are rejected. Error messages do not expose upstream responses.
- The backend continues to acknowledge speech through the existing
  owner-scoped `browser_speech_done` route. SPARK's Chromium AEC microphone
  remains gated throughout synthesis and playback; it returns to the exact
  existing user mute state after a completion, failure or cancellation.
- Source/protocol: https://github.com/debpalash/VoiceStudio/blob/main/backend/api/routers/openai_compat.py
  and https://github.com/debpalash/VoiceStudio/blob/main/docs/speech-platform.md
- VoiceStudio software: AGPL-3.0; individual model weights have separate
  restrictions. No VoiceStudio source was copied into SPARK.

## Qualification and limitations

```powershell
npm test
npm run build
python -m unittest discover -s tests -p test_spark_windows_speech.py
```

The tests use synthetic local audio; they **do not establish** that
VoiceStudio is installed on the user's Windows machine, that their model
fits RAM/disk limits, or that a live voice played through speakers. Local
Windows/Electron acceptance still needs a real VoiceStudio install, a
successful Groq AEC connection and an audible response. Text continues to
go to the selected Groq model; this adapter makes the TTS path local only.
The 180-second speech acknowledgement timeout is a failure bound, not a
speed or latency guarantee.

No SPARK voice feature grants authority to purchase, modify VYNDI business
records, or send external messages.
