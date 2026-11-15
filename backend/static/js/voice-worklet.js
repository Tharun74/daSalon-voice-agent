// Resample the browser's actual sample rate to mono PCM16 at 16 kHz.
class VoiceCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = [];
    this.position = 0;
    this.output = [];
  }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    this.samples.push(...channel);
    const step = sampleRate / 16000;
    while (this.position + 1 < this.samples.length) {
      const i = Math.floor(this.position), f = this.position - i;
      const value = this.samples[i] * (1-f) + this.samples[i+1] * f;
      this.output.push(Math.round(Math.max(-1, Math.min(1, value)) * 32767));
      this.position += step;
      if (this.output.length === 320) {
        const pcm = new Int16Array(this.output);
        const rms = Math.sqrt(pcm.reduce((n, v) => n + (v / 32768) ** 2, 0) / pcm.length);
        this.port.postMessage({pcm: pcm.buffer, rms}, [pcm.buffer]);
        this.output = [];
      }
    }
    const used = Math.floor(this.position);
    this.samples.splice(0, used);
    this.position -= used;
    return true;
  }
}
registerProcessor('voice-capture', VoiceCapture);
