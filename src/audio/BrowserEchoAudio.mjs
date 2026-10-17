/* SPARK browser audio bridge.
   Mic and model playback run through ONE Chromium AudioContext so the browser
   can use the far-end render reference for acoustic echo cancellation.
   The Gemini key stays in Python; Socket.IO carries only raw PCM.
   No audio is recorded or saved to local files.
*/
export class BrowserEchoAudio {
  constructor({socket, onError = () => {}}) {
    this.socket = socket;
    this.onError = onError;
    this.audioContext = null;
    this.stream = null;
    this.input = null;
    this.worklet = null;
    this.ready = false;
    this.muted = true;
    this.closed = false;
    this.playUntil = 0;
    this.sources = new Set();
    this.onSpeaker = data => {
      try { this.playPcm(data); }
      catch (err) { this.onError('SPARK browser speaker failed: ' + String(err?.message || 'unknown')); }
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
      if (!track || track.getSettings().echoCancellation !== true) {
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
    } catch (e) {
      this.stop();
      throw e;
    }
  }

  setMuted(muted) {
    this.muted = Boolean(muted);
    this.worklet?.port.postMessage({type: 'enabled', enabled: this.ready && !this.muted});
  }

  playPcm(payload) {
    if (!this.ready || this.closed || !this.audioContext) return;
    const bytes = payload instanceof ArrayBuffer ? new Uint8Array(payload)
      : ArrayBuffer.isView(payload) ? new Uint8Array(payload.buffer, payload.byteOffset, payload.byteLength)
      : null;
    if (!bytes || !bytes.byteLength || bytes.byteLength % 2 || bytes.byteLength > 262144) return;
    const ctx = this.audioContext;
    const samples = bytes.byteLength / 2;
    const buffer = ctx.createBuffer(1, samples, 24000);
    const target = buffer.getChannelData(0);
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    for (let i = 0; i < samples; i++) target[i] = view.getInt16(i * 2, true) / 32768;
    const startAt = Math.max(ctx.currentTime + 0.025, this.playUntil);
    if (startAt - ctx.currentTime > 6) {
      this.onError('Speaker queue exceeded six seconds. Pausing output to prevent runaway playback.');
      return;
    }
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.onended = () => {
      this.sources.delete(source);
      source.disconnect();
    };
    this.sources.add(source);
    source.start(startAt);
    this.playUntil = startAt + buffer.duration;
  }

  stop() {
    this.closed = true;
    this.ready = false;
    this.setMuted(true);
    this.socket.off('browser_audio', this.onSpeaker);
    for (const source of this.sources) {
      try { source.stop(); source.disconnect(); } catch (_) {}
    }
    this.sources.clear();
    this.worklet?.disconnect();
    this.input?.disconnect();
    for (const track of this.stream?.getTracks() || []) track.stop();
    this.audioContext?.close().catch(() => {});
    this.worklet = null;
    this.input = null;
    this.stream = null;
    this.audioContext = null;
    this.playUntil = 0;
  }
}
