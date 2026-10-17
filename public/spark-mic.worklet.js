/* SPARK's Chromium audio capture: browser echo cancellation precedes this worklet.
   Continuous mono PCM at 16kHz, emitted in ~100ms binary chunks.
   Worklet output is ALWAYS silent: no local microphone monitor or feedback. */
class SparkMicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.enabled = false;
    this.phase = 0;
    this.sum = 0;
    this.count = 0;
    this.buffer = new Int16Array(1600);
    this.offset = 0;
    this.port.onmessage = ({data}) => {
      if (data?.type === 'enabled') {
        this.enabled = Boolean(data.enabled);
        if (!this.enabled) {
          this.offset = 0;
          this.phase = 0;
          this.sum = 0;
          this.count = 0;
        }
      }
    };
  }
  process(inputs, outputs) {
    for (const output of outputs[0] || []) output.fill(0);
    if (!this.enabled) return true;
    const samples = inputs[0]?.[0];
    if (!samples) return true;
    for (let i = 0; i < samples.length; i++) {
      this.sum += samples[i];
      this.count++;
      this.phase += 16000;
      if (this.phase >= sampleRate) {
        this.phase -= sampleRate;
        const value = Math.max(-1, Math.min(1, this.sum / this.count));
        this.buffer[this.offset++] = Math.max(-32768, Math.min(32767, Math.round(value * 32767)));
        this.sum = 0;
        this.count = 0;
        if (this.offset === 1600) {
          this.port.postMessage({type: 'pcm', pcm: this.buffer.buffer}, [this.buffer.buffer]);
          this.buffer = new Int16Array(1600);
          this.offset = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor('spark-mic-capture', SparkMicProcessor);
