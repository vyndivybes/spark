# Morning Digest voice correction

The owner reported that Windows speech was being transcribed as their own
voice, provoking unrelated Gemini replies and weather searches.

Morning Digest's product playback now submits its saved text to the owning
SPARK Gemini Live session. The session's existing PCM speaker and microphone
gate handle playback. The UI button, typed playback command and microphone
command use this path. Disconnected or foreign sessions are refused; the
product does not fall back to Windows speech. Narration instructions require
the saved digest and prohibit unrelated searches or replacement summaries.

Verification: 49 Python tests and 86 subtests passed, including owner/session
checks, Gemini microphone command routing and refusal to launch subprocess
speech. Seven Node checks, Python compilation and the frontend build passed.
SPARK was closed normally and reopened to load the change. A real audible
Gemini digest remains to be confirmed by the owner after connecting voice;
test submission is not a claim of completed playback.
