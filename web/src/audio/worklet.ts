// AudioWorklet processor source (inlined as a Blob URL so no extra asset path is needed).
// Capture: converts Float32 mic frames → PCM16 LE at the context rate, posts 20 ms chunks.
// Playout: pulls PCM16 from a ring buffer filled by the main thread; reports underruns and playhead.
export const WORKLET_SOURCE = `
class QevionCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = [];
    this.len = 0;
    this.chunk = Math.round(sampleRate * 0.02); // 20 ms
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    this.buf.push(Float32Array.from(ch));
    this.len += ch.length;
    while (this.len >= this.chunk) {
      const out = new Int16Array(this.chunk);
      let need = this.chunk, o = 0;
      while (need > 0) {
        const head = this.buf[0];
        const take = Math.min(need, head.length);
        for (let i = 0; i < take; i++) {
          const s = Math.max(-1, Math.min(1, head[i]));
          out[o++] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        if (take === head.length) this.buf.shift(); else this.buf[0] = head.subarray(take);
        need -= take;
      }
      this.len -= this.chunk;
      this.port.postMessage(out.buffer, [out.buffer]);
    }
    return true;
  }
}
class QevionPlayout extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.offset = 0;
    this.played = 0;
    this.underruns = 0;
    this.idle = true;
    this.port.onmessage = (e) => {
      if (e.data === 'flush') { this.queue = []; this.offset = 0; this.idle = true; this.port.postMessage({ type: 'flushed', played: this.played }); return; }
      this.queue.push(new Int16Array(e.data));
    };
  }
  process(_inputs, outputs) {
    const out = outputs[0][0];
    let i = 0;
    while (i < out.length) {
      if (this.queue.length === 0) {
        if (i === 0) this.underruns++;
        this.idle = true;
        for (; i < out.length; i++) out[i] = 0;
        break;
      }
      const head = this.queue[0];
      const v = head[this.offset++];
      // latency diagnostics: report the render time of the first audible sample after an idle queue
      if (this.idle && v !== 0) { this.idle = false; this.port.postMessage({ type: 'first_sample', at: currentTime + i / sampleRate }); }
      out[i++] = v / 0x8000;
      this.played++;
      if (this.offset >= head.length) { this.queue.shift(); this.offset = 0; }
    }
    if ((this.played % (sampleRate / 10)) < out.length) {
      this.port.postMessage({ type: 'tick', played: this.played, queued: this.queue.reduce((a, q) => a + q.length, 0) - this.offset, underruns: this.underruns });
    }
    return true;
  }
}
registerProcessor('qevion-capture', QevionCapture);
registerProcessor('qevion-playout', QevionPlayout);
`;

export function workletUrl(): string {
  return URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: "application/javascript" }));
}
