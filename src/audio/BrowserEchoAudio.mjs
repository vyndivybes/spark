/* SPARK browser audio bridge.
   Mic and model playback run through ONE Chromium AudioContext so the browser
   can use the far-end render reference for acoustic echo cancellation.
   The Gemini key stays in Python; Socket.IO carries only raw PCM.
   No audio is recorded or saved to local files.
*/
export class BrowserEchoAudio {
  constructor({socket, onError = () => {}, onWarning = () => {}}) {
    this.socket = socket;
    this.onError = onError;
    this.onWarning = onWarning;
    this.audioContext = null;
    this.stream = null;
    this.input = null;
    this.analyser = null;
    this.spectrumBins = null;
    this.worklet = null;
    this.ready = false;
    this.muted = true;
    this.closed = false;
    this.playUntil = 0;
    this.sources = new Set();
    // Gemini often delivers audio ahead of real time. Keep it in a bounded
    // queue and schedule playback just ahead of the hardware clock.
    this.pendingPcm = [];
    this.pendingSeconds = 0;
    this.maxPendingSeconds = 90;
    this.scheduleAheadSeconds = 1.75;
    this.warnedOverflow = false;
    this.pumpTimer = null;
    this.onSpeaker = data => {
      if (this.closed) return;
      try { this.playPcm(data); }
      catch (err) { this.failSpeaker(err); }
    };
  }

  async start({deviceId = '', outputId = ''} = {}) {
    if (this.ready) return;
    this.closed = false;
    try {
      if (!navigator?.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
        throw new Error('Chromium microphone echo cancellation is unavailable.');
      }
      const audio = {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      };
      if (deviceId && deviceId !== 'default') audio.deviceId = {exact: deviceId};
      this.stream = await navigator.mediaDevices.getUserMedia({audio, video: false});
      if (this.closed) throw new Error('SPARK audio cancelled.');
      const track = this.stream.getAudioTracks()[0];
      // Digital output-monitor devices bypass normal acoustic AEC and can
      // create an endless model-to-model audio loop. Never use them as mic.
      if (/stereo mix|what u hear|loopback/i.test(track?.label || '')) {
        throw new Error('Select a real microphone; Stereo Mix and loopback inputs are unsafe for hands-free voice.');
      }
      const echoMode = track?.getSettings()?.echoCancellation;
      // Chromium may return boolean true or the stronger string "all".
      // "remote-only" cannot be trusted to cancel local Web Audio playback.
      if (echoMode !== true && echoMode !== 'all') {
        throw new Error('Microphone echo cancellation is not active. Choose a compatible input device.');
      }
      const Context = window.AudioContext || window.webkitAudioContext;
      this.audioContext = new Context({latencyHint: 'interactive'});
      if (outputId && outputId !== 'default') {
        if (typeof this.audioContext.setSinkId !== 'function') {
          throw new Error('Selected speaker cannot be routed through Chromium AEC. Use system default.');
        }
        await this.audioContext.setSinkId(outputId);
      }
      const workletUrl = new URL('./spark-mic.worklet.js', window.location.href).href;
      await this.audioContext.audioWorklet.addModule(workletUrl);
      if (this.closed) throw new Error('SPARK audio cancelled.');
      this.input = this.audioContext.createMediaStreamSource(this.stream);
      // Tap the approved input stream for local visualization. This branch has
      // no speaker connection and never opens another microphone stream.
      this.analyser = this.audioContext.createAnalyser?.();
      if (this.analyser) {
        this.analyser.fftSize = 512;
        this.analyser.smoothingTimeConstant = .65;
        this.spectrumBins = new Uint8Array(this.analyser.frequencyBinCount);
        this.input.connect(this.analyser);
      }
      this.worklet = new AudioWorkletNode(this.audioContext, 'spark-mic-capture');
      this.worklet.port.onmessage = ({data}) => {
        if (!this.ready || this.muted || !this.socket.connected || data?.type !== 'pcm') return;
        if (!(data.pcm instanceof ArrayBuffer) || data.pcm.byteLength !== 3200) return;
        this.socket.emit('browser_mic_pcm', new Uint8Array(data.pcm));
      };
      // The worklet outputs silence so no raw mic is heard locally.
      this.input.connect(this.worklet);
      this.worklet.connect(this.audioContext.destination);
      this.socket.on('browser_audio', this.onSpeaker);
      await this.audioContext.resume();
      if (this.closed || this.audioContext.state !== 'running') {
        throw new Error('Audio playback requires a user gesture or a working Windows sound device.');
      }
      this.ready = true;
      this.setMuted(false);
      // The WebAudio clock advances independently of incoming Socket.IO
      // packets; drain only a small window ahead to keep speech continuous.
      this.pumpTimer = setInterval(() => {
        try { this.pumpAudio(); }
        catch (err) { this.failSpeaker(err); }
      }, 80);
    } catch (e) {
      this.stop();
      throw e;
    }
  }

  setMuted(muted) {
    this.muted = Boolean(muted);
    this.worklet?.port.postMessage({type: 'enabled', enabled: this.ready && !this.muted});
  }

  readSpectrum() {
    if (!this.ready || this.closed || this.muted || !this.analyser) return null;
    this.analyser.getByteFrequencyData(this.spectrumBins);
    return {bins:this.spectrumBins,sampleRate:this.audioContext.sampleRate,fftSize:this.analyser.fftSize};
  }

  failSpeaker(err) {
    // A *real* Chromium playback exception disables the microphone to avoid
    // streaming into a broken AEC reference. Report only one failure.
    if (this.closed) return;
    const message = 'SPARK browser speaker failed: ' + String(err?.message || 'unknown');
    this.stop();
    this.onError(message);
  }

  playPcm(payload) {
    if (!this.ready || this.closed || !this.audioContext) return;
    const bytes = payload instanceof ArrayBuffer ? new Uint8Array(payload)
      : ArrayBuffer.isView(payload) ? new Uint8Array(payload.buffer, payload.byteOffset, payload.byteLength)
      : null;
    if (!bytes || !bytes.byteLength || bytes.byteLength % 2 || bytes.byteLength > 262144) return;
    const ctx = this.audioContext;
    const samples = bytes.byteLength / 2;
    const seconds = samples / 24000;
    // Keep the response intact during normal fast generation. An actual
    // runaway stream (>90 s queued) is a nonfatal backlog warning, not a
    // nonexistent Windows microphone or speaker device.
    const scheduledSeconds = Math.max(0, this.playUntil - ctx.currentTime);
    if (this.pendingSeconds + scheduledSeconds + seconds > this.maxPendingSeconds) {
      if (!this.warnedOverflow) {
        this.warnedOverflow = true;
        this.onWarning('SPARK received over 90 seconds of queued speech. Excess audio was skipped, but hands-free microphone and speakers remain available.');
      }
      return;
    }
    const buffer = ctx.createBuffer(1, samples, 24000);
    const target = buffer.getChannelData(0);
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    for (let n = 0; n < samples; n++) target[n] = view.getInt16(n * 2, true) / 32768;
    this.pendingPcm.push(buffer);
    this.pendingSeconds += buffer.duration;
    this.pumpAudio();
  }

  pumpAudio() {
    if (!this.ready || this.closed || !this.audioContext) return;
    const ctx = this.audioContext;
    if (ctx.state && ctx.state !== 'running') return;
    // Do not schedule the entire server-generated response at once.
    // Chromium playback remains ordered while its real-time clock advances.
    while (this.pendingPcm.length &&
           Math.max(0, this.playUntil - ctx.currentTime) < this.scheduleAheadSeconds) {
      const buffer = this.pendingPcm.shift();
      this.pendingSeconds = Math.max(0, this.pendingSeconds - buffer.duration);
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(ctx.destination);
      source.onended = () => {
        this.sources.delete(source);
        source.disconnect();
      };
      const startAt = Math.max(ctx.currentTime + 0.025, this.playUntil);
      this.sources.add(source);
      source.start(startAt);
      this.playUntil = startAt + buffer.duration;
    }
    // Once the backlog clears, later congestions may warrant a new notice.
    if (this.pendingSeconds < 5 && this.playUntil - ctx.currentTime < 5) {
      this.warnedOverflow = false;
    }
  }

  stop() {
    this.closed = true;
    this.ready = false;
    this.setMuted(true);
    if (this.pumpTimer !== null) {
      clearInterval(this.pumpTimer);
      this.pumpTimer = null;
    }
    this.pendingPcm = [];
    this.pendingSeconds = 0;
    this.warnedOverflow = false;
    this.socket.off('browser_audio', this.onSpeaker);
    for (const source of this.sources) {
      try { source.stop(); source.disconnect(); } catch (_) {}
    }
    this.sources.clear();
    this.worklet?.disconnect();
    this.input?.disconnect();
    this.analyser?.disconnect();
    this.analyser = null;
    this.spectrumBins = null;
    for (const track of this.stream?.getTracks() || []) track.stop();
    // A cancelled or failed AudioContext may not expose a usable close()
    // method on mocked / partially initialized devices.
    try {
      this.audioContext?.close?.()?.catch?.(() => {});
    } catch (_) { /* already closed or device initialization failed */ }
    this.worklet = null;
    this.input = null;
    this.stream = null;
    this.audioContext = null;
    this.playUntil = 0;
  }
}
