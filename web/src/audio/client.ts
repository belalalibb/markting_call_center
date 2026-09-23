// Browser voice client: mic → PCM16 24 kHz → WS binary frames; WS binary → playout worklet.
// Emits playout_started/playout_stopped timestamps so the runtime can measure the 7-step interruption (§31).
import { workletUrl } from "./worklet";

export const TARGET_RATE = 24000;

export interface VoiceClientEvents {
  onStatus?: (s: string) => void;
  onLevel?: (rms: number) => void;
  onPlayoutStats?: (s: { played_ms: number; queued_ms: number; underruns: number }) => void;
}

export class VoiceClient {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private capture: AudioWorkletNode | null = null;
  private playout: AudioWorkletNode | null = null;
  private _sending = false;
  private _resampleCarry: Float32Array = new Float32Array(0);
  public bytesOut = 0;
  public bytesIn = 0;
  public playing = false;
  private currentResponse: string | null = null;

  constructor(
    private send: (frame: ArrayBuffer) => void,
    private control: (msg: Record<string, unknown>) => void,
    private ev: VoiceClientEvents = {},
  ) {}

  async start(): Promise<void> {
    if (this.ctx) return;
    this.ctx = new AudioContext({ sampleRate: TARGET_RATE, latencyHint: "interactive" });
    await this.ctx.audioWorklet.addModule(workletUrl());
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.capture = new AudioWorkletNode(this.ctx, "qevion-capture", { numberOfInputs: 1, numberOfOutputs: 0 });
    this.capture.port.onmessage = (e: MessageEvent<ArrayBuffer>) => this.onCapture(e.data);
    src.connect(this.capture);
    this.playout = new AudioWorkletNode(this.ctx, "qevion-playout", { numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [1] });
    this.playout.port.onmessage = (e: MessageEvent<{ type: string; played: number; queued?: number; underruns?: number }>) => {
      if (e.data.type === "tick") {
        const played_ms = (e.data.played / (this.ctx?.sampleRate ?? TARGET_RATE)) * 1000;
        const queued_ms = ((e.data.queued ?? 0) / (this.ctx?.sampleRate ?? TARGET_RATE)) * 1000;
        this.ev.onPlayoutStats?.({ played_ms, queued_ms, underruns: e.data.underruns ?? 0 });
        if (this.playing && queued_ms < 1 && this.currentResponse) this.markStopped("drained");
      }
    };
    this.playout.connect(this.ctx.destination);
    this._sending = true;
    this.ev.onStatus?.(`mic on @ ${this.ctx.sampleRate} Hz`);
  }

  private onCapture(buf: ArrayBuffer): void {
    if (!this._sending || !this.ctx) return;
    let pcm = buf;
    if (this.ctx.sampleRate !== TARGET_RATE) pcm = this.resample(new Int16Array(buf), this.ctx.sampleRate);
    const i16 = new Int16Array(pcm);
    let acc = 0;
    for (let i = 0; i < i16.length; i += 8) acc += (i16[i] ?? 0) ** 2;
    this.ev.onLevel?.(Math.sqrt(acc / Math.max(1, i16.length / 8)) / 32768);
    this.bytesOut += pcm.byteLength;
    this.send(pcm);
  }

  /** Linear resample Int16 at `from` Hz → TARGET_RATE (browsers that refuse a 24 kHz context). */
  private resample(input: Int16Array, from: number): ArrayBuffer {
    const ratio = from / TARGET_RATE;
    const merged = new Float32Array(this._resampleCarry.length + input.length);
    merged.set(this._resampleCarry);
    for (let i = 0; i < input.length; i++) merged[this._resampleCarry.length + i] = (input[i] ?? 0) / 32768;
    const outLen = Math.floor((merged.length - 1) / ratio);
    const out = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const pos = i * ratio;
      const j = Math.floor(pos);
      const frac = pos - j;
      const a = merged[j] ?? 0;
      const b = merged[j + 1] ?? a;
      out[i] = Math.max(-32768, Math.min(32767, Math.round((a + (b - a) * frac) * 32767)));
    }
    const consumed = Math.floor(outLen * ratio);
    this._resampleCarry = merged.slice(consumed);
    return out.buffer;
  }

  /** Server audio frame (PCM16 @ TARGET_RATE) → playout ring. */
  enqueue(frame: ArrayBuffer, responseId: string | null): void {
    if (!this.playout) return;
    this.bytesIn += frame.byteLength;
    if (!this.playing) {
      this.playing = true;
      this.currentResponse = responseId;
      this.control({ type: "playout_started", response_id: responseId, client_ts_ms: Date.now() });
    }
    const copy = frame.slice(0);
    this.playout.port.postMessage(copy, [copy]);
  }

  /** Interruption step 2 (§31): drop everything queued locally within one render quantum. */
  stopPlayout(reason = "stop_playout"): void {
    this.playout?.port.postMessage("flush");
    this.markStopped(reason);
  }

  private markStopped(reason: string): void {
    if (!this.playing) return;
    this.playing = false;
    this.control({ type: "playout_stopped", response_id: this.currentResponse, client_ts_ms: Date.now(), text: reason });
    this.currentResponse = null;
  }

  async stop(): Promise<void> {
    this._sending = false;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.capture?.disconnect();
    this.playout?.disconnect();
    await this.ctx?.close();
    this.ctx = null;
    this.stream = null;
    this.capture = null;
    this.playout = null;
    this.ev.onStatus?.("mic off");
  }
}
