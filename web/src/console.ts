// Operator Console: live text/voice session over WS (selectable composition), state, events, handoffs,
// and the §31 interruption watermarks (t0..t4) per session.
import { api, outboundWsUrl, wsUrl, type ActivitySummary, type CompositionSummary, type ContactState, type InterruptionRecord } from "./api";
import { VoiceClient, latencyMark } from "./audio/client";
import { clear, errMsg, h, pill, pre, section, table, toast, toneFor } from "./ui";

interface ServerMsg {
  type: string;
  session_id: string;
  response_id?: string | null;
  text?: string | null;
  payload: Record<string, unknown>;
}

let ws: WebSocket | null = null;
let voice: VoiceClient | null = null;
let currentSid: string | null = null;

let stateRedraw: (m: ServerMsg) => void = () => {};
let sessionsRedraw: () => Promise<void> = async () => {};
let eventsPush: (m: ServerMsg) => void = () => {};
let interruptionsPush: (p: Record<string, unknown>) => void = () => {};

export async function renderConsole(root: HTMLElement): Promise<void> {
  root.className = "";
  clear(root);
  const [activities, compositions] = await Promise.all([
    api.activities().catch(() => [] as ActivitySummary[]),
    api.compositions().catch(() => [] as CompositionSummary[]),
  ]);
  // P4: Normal mode = what an operator needs to run a call; Advanced adds engineering telemetry.
  const adv = (el: HTMLElement) => { el.classList.add("advanced"); return el; };
  root.append(
    chatCard(activities, compositions),
    sessionsCard(),
    adv(stateCard()),
    adv(outboundCard(activities)),
    adv(interruptionsCard()),
    adv(eventsCard()),
  );
}

// ------------------------------------------------------- outbound dial (QV-OUT-DIR / QV-TEL seam)
let outboundWs: WebSocket | null = null;

function outboundCard(activities: ActivitySummary[]): HTMLElement {
  const box = h("div");
  const card = section("Outbound dial (contact policy → simulated telephony → same Core)", box);
  const outbound = activities.filter((a) => a.direction === "outbound");
  const sel = h("select", {}, ...(outbound.length ? outbound : activities).map((a) => h("option", { value: a.key }, `${a.key} — ${a.name} [${a.direction}]`)));
  const ref = h("input", { value: "contact_demo_1", placeholder: "contact_ref" });
  const consent = h("select", {}, h("option", { value: "unknown" }, "consent: unknown"), h("option", { value: "true" }, "consent: given"), h("option", { value: "false" }, "consent: refused"));
  const optOut = h("input", { type: "checkbox" });
  const suppressed = h("input", { type: "checkbox" });
  const decisionHost = h("div");
  const chat = h("div", { class: "chat" });
  const input = h("input", { placeholder: "type as the called party…" });
  const statusHost = h("span");
  const setStatus = (t: string, tone: "ok" | "muted" | "bad" | "warn") => { clear(statusHost); statusHost.append(pill(t, tone)); };
  setStatus("idle", "muted");
  const add = (cls: string, text: string) => { chat.append(h("div", { class: `msg ${cls}` }, text)); chat.scrollTop = chat.scrollHeight; };
  const send = (obj: Record<string, unknown>) => {
    if (outboundWs && outboundWs.readyState === WebSocket.OPEN) outboundWs.send(JSON.stringify({ schema: "qevion.transport.v1", client_ts_ms: Date.now(), ...obj }));
  };
  const showContact = (c: ContactState) => {
    consent.value = c.consent === null ? "unknown" : String(c.consent);
    optOut.checked = c.opted_out; suppressed.checked = c.suppressed;
    return pill(`attempts: ${c.attempts}`, c.attempts ? "warn" : "muted");
  };
  const saveContact = async (): Promise<ContactState> => api.setContact(ref.value, {
    consent: consent.value === "unknown" ? null : consent.value === "true",
    opted_out: optOut.checked, suppressed: suppressed.checked,
  });
  const check = async () => {
    clear(decisionHost);
    try {
      const c = await saveContact();
      const d = await api.contactCheck(sel.value, ref.value);
      decisionHost.append(h("div", { class: "row" }, pill(d.allowed ? "contact ALLOWED" : "contact REFUSED", d.allowed ? "ok" : "bad"),
        ...d.refusals.map((r) => pill(r, "bad")), showContact(c), h("span", { class: "muted" }, `checked ${d.checked_at}`)));
    } catch (e) { toast(errMsg(e), "bad"); }
  };
  const dial = async () => {
    outboundWs?.close();
    clear(chat);
    try { await saveContact(); } catch (e) { toast(errMsg(e), "bad"); return; }
    outboundWs = new WebSocket(outboundWsUrl(sel.value, ref.value));
    outboundWs.binaryType = "arraybuffer";
    outboundWs.onopen = () => { setStatus("dialing…", "warn"); add("sys", `dial → ${sel.value} / ${ref.value}`); };
    outboundWs.onclose = (e) => {
      const why = e.code === 4403 ? "refused by contact policy" : e.code === 4480 ? "not answered" : e.code === 4400 ? "inbound-only activity" : e.code === 4404 ? "activity not found" : "closed";
      setStatus(`${why} (${e.code})`, e.code >= 4400 ? "bad" : "muted");
      add("sys", `${why}${e.reason ? ": " + e.reason : ""}`);
      void refreshAttempts(); void sessionsRedraw();
    };
    outboundWs.onerror = () => { setStatus("error", "bad"); };
    outboundWs.onmessage = (ev) => {
      if (typeof ev.data !== "string") return;
      const m = JSON.parse(ev.data) as ServerMsg;
      currentSid = m.session_id;
      eventsPush(m);
      switch (m.type) {
        case "ready": setStatus("answered · live", "ok"); add("sys", "call answered — session ready"); break;
        case "transcript": add(m.payload["role"] === "user" ? "user" : "agent", m.text ?? ""); break;
        case "audio_start": add("agent", m.text ? m.text : "(speaking…)"); send({ type: "playout_started", response_id: m.response_id }); break;
        case "audio_end": send({ type: "playout_stopped", response_id: m.response_id }); break;
        case "stop_playout": add("sys", "⏹ interrupted"); send({ type: "playout_stopped", response_id: m.response_id }); break;
        case "confirmation_request": {
          const row = h("div", { class: "msg sys" }, `Confirm: ${m.text ?? JSON.stringify(m.payload)} `,
            h("button", { onClick: () => { send({ type: "confirm", call_id: m.payload["call_id"], granted: true }); row.remove(); } }, "Yes"),
            h("button", { onClick: () => { send({ type: "confirm", call_id: m.payload["call_id"], granted: false }); row.remove(); } }, "No"));
          chat.append(row); break;
        }
        case "state": stateRedraw(m); break;
        case "error": add("sys", `error: ${m.text}`); break;
        case "bye": add("sys", "agent closed the call"); break;
        default: break;
      }
    };
  };
  const attempts = h("div");
  const refreshAttempts = async () => {
    clear(attempts);
    try {
      const rows = await api.outboundAttempts();
      if (!rows.length) { attempts.append(h("p", { class: "muted" }, "No outbound attempts yet. Every attempt is recorded, including refusals.")); return; }
      attempts.append(table(["attempt", "activity", "contact", "decision", "call", "session"], rows.slice().reverse().map((a) => [
        h("code", {}, String(a.attempt_id).slice(0, 12)), String(a.activity_key), String(a.contact_ref),
        a.contact_decision.allowed ? pill("allowed", "ok") : pill(`refused: ${a.contact_decision.refusals.join(",")}`, "bad"),
        a.call_state ? pill(String(a.call_state), a.call_state === "answered" ? "ok" : "warn") : "—",
        a.session_id ? h("code", {}, String(a.session_id).slice(0, 14)) : "—",
      ])));
    } catch (e) { attempts.append(h("p", { class: "muted" }, errMsg(e))); }
  };
  const doSend = () => { const t = input.value.trim(); if (!t) return; add("user", t); send({ type: "text", text: t }); input.value = ""; };
  input.addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") doSend(); });
  box.append(
    h("p", { class: "muted" }, "Contact-policy hooks (consent · opt-out · suppression · attempt limit · contact window) are evaluated before any dial. A refusal is recorded and closes with 4403; no-answer with 4480."),
    h("div", { class: "row" }, sel, ref),
    h("div", { class: "row" }, consent, h("label", {}, optOut, " opted out"), h("label", {}, suppressed, " suppressed"),
      h("button", { onClick: () => void check() }, "Check contact policy"),
      h("button", { class: "primary", onClick: () => void dial() }, "📞 Dial"),
      h("button", { class: "danger", onClick: () => send({ type: "bye" }) }, "Hang up"), statusHost),
    decisionHost, chat,
    h("div", { class: "row" }, input, h("button", { onClick: doSend }, "Send")),
    h("h3", {}, "Outbound attempts (audit)"), attempts,
  );
  void refreshAttempts();
  return card;
}

function compLabel(c: CompositionSummary): string {
  // F-14: mock = simulation, needs no key; real providers say whether a key is present
  const state = c.simulated ? "simulated (no key needed)"
    : c.ready ? `real provider · key: ${c.credential_source}` : "real provider · KEY MISSING → Admin";
  return `${c.composition_id}${c["default"] ? " (default)" : ""} — ${state}`;
}

/** F-14: actionable text for runtime error codes (what happened + what to do). */
export function explainError(code: string, text: string): string {
  switch (code) {
    case "provider_credential_missing":
      return "No provider key for this composition. Open Admin → Ephemeral test key, paste the key, then Connect again.";
    case "provider_failure":
      return `The voice provider failed (${text}). Check the key in Admin and your network, then reconnect.`;
    case "provider_request_rejected":
      return `The provider rejected one request (${text}); the session continues.`;
    default:
      return text;
  }
}

/** F-14: the browser's getUserMedia error names → what the operator should do. */
export function explainMicError(e: unknown): string {
  const name = e instanceof DOMException ? e.name : e instanceof Error ? e.name : "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Microphone blocked. Click the lock/camera icon in the address bar → allow Microphone, then press Mic again. (Needs https or localhost.)";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No microphone found. Plug one in or pick an input device in your OS settings.";
    case "NotReadableError":
      return "The microphone is in use by another app. Close it and try again.";
    default:
      return `Microphone unavailable: ${errMsg(e)}. You can still use the text channel.`;
  }
}

function chatCard(activities: ActivitySummary[], compositions: CompositionSummary[]): HTMLElement {
  const box = h("div");
  const card = section("Live session (text or browser voice)", box);
  const sel = h("select", {}, ...activities.map((a) => h("option", { value: a.key }, `${a.key} — ${a.name} [${a.readiness}]`)));
  const compSel = h("select", {},
    h("option", { value: "pinned" }, "pinned — use the activity's pinned composition"),
    ...compositions.map((c) => h("option", { value: c.composition_id }, compLabel(c))));
  const def = compositions.find((c) => c["default"]);
  if (def) compSel.value = def.composition_id;
  const micBtn = h("button", {}, "🎙 Mic off");
  const meter = h("span", { class: "meter" }, h("span", { class: "meter-fill" }));
  const fill = meter.firstElementChild as HTMLElement;
  const chat = h("div", { class: "chat" });
  const input = h("input", { placeholder: "type as the caller… (try a question, field values, or 'stop')" });
  const statusHost = h("span");
  const voiceStatus = h("span", { class: "muted" }, "");
  const setStatus = (t: string, tone: "ok" | "muted" | "bad") => { clear(statusHost); statusHost.append(pill(t, tone)); };
  setStatus("disconnected", "muted");
  const add = (cls: string, text: string) => { chat.append(h("div", { class: `msg ${cls}` }, text)); chat.scrollTop = chat.scrollHeight; };
  const send = (obj: Record<string, unknown>) => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ schema: "qevion.transport.v1", client_ts_ms: Date.now(), ...obj }));
  };
  const sendFrame = (frame: ArrayBuffer) => { if (ws && ws.readyState === WebSocket.OPEN) ws.send(frame); };
  let lastResponseId: string | null = null;
  let audioBytesIn = 0;
  let firstRecv: string | null = null;
  const agentBubbles = new Map<string, HTMLElement>();

  const micOff = async () => {
    if (!voice) return;
    await voice.stop();
    voice = null;
    micBtn.textContent = "🎙 Mic off";
    fill.style.width = "0%";
    voiceStatus.textContent = "";
  };
  const micOn = async () => {
    if (voice) return;
    const v = new VoiceClient(sendFrame, send, {
      onStatus: (s) => { voiceStatus.textContent = s; },
      onLevel: (rms) => { fill.style.width = `${Math.min(100, Math.round(rms * 400))}%`; },
    });
    try {
      await v.start();
      voice = v;
      micBtn.textContent = "🎙 Mic on";
    } catch (e) {
      const why = explainMicError(e);
      toast(why, "bad");
      voiceStatus.textContent = why;
    }
  };
  micBtn.addEventListener("click", () => void (voice ? micOff() : micOn()));

  const connect = () => {
    ws?.close();
    clear(chat);
    audioBytesIn = 0;
    const channel = voice ? "browser_voice" : "text";
    ws = new WebSocket(wsUrl(sel.value, channel, compSel.value));
    ws.binaryType = "arraybuffer";
    let heartbeats = 0;
    ws.onopen = () => { setStatus(`connecting · ${channel}`, "ok"); add("sys", `connected → ${sel.value} via ${compSel.value === "pinned" ? "pinned composition" : compSel.value} (${channel}) — waiting for session ready…`); send({ type: "hello" }); };
    ws.onclose = (e) => {
      setStatus(`disconnected (${e.code})`, e.code === 1000 ? "muted" : "bad");
      add("sys", `closed (${e.code}${e.reason ? ": " + e.reason : ""})${e.code === 1011 ? " — keepalive/protocol failure, see Sessions card close_code" : ""}`);
      voice?.stopPlayout("socket_closed");
      window.dispatchEvent(new CustomEvent("qevion:live", { detail: null }));
      void sessionsRedraw();
    };
    ws.onerror = () => { setStatus("error", "bad"); add("sys", "socket error"); };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") {
        const buf = ev.data as ArrayBuffer;
        if (lastResponseId !== firstRecv) { firstRecv = lastResponseId; latencyMark("first_frame_ws_recv", lastResponseId); }
        audioBytesIn += buf.byteLength;
        if (voice) voice.enqueue(buf, lastResponseId);
        else if (audioBytesIn === buf.byteLength) add("sys", `◼ audio stream started (${buf.byteLength} bytes; mic off → not played)`);
        return;
      }
      const m = JSON.parse(ev.data) as ServerMsg;
      currentSid = m.session_id;
      eventsPush(m);
      switch (m.type) {
        case "ready": {
          // Actual session facts from the runtime (not the selector): composition / channel / provider / credential.
          const comp = String(m.payload["composition_id"] ?? compSel.value);
          const ch = String(m.payload["channel"] ?? channel);
          const prov = `${String(m.payload["s2s_provider"] ?? "?")}:${String(m.payload["s2s_model"] ?? "?")}`;
          const cred = String(m.payload["credential_source"] ?? "none");
          setStatus(`live · ${comp} · ${ch}`, "ok");
          add("sys", `session ready — composition ${comp} · ${ch} · s2s ${prov} · credential ${cred}`);
          window.dispatchEvent(new CustomEvent("qevion:live", { detail: { composition: comp, channel: ch, provider: prov } }));
          break;
        }
        case "ping":
          // Application heartbeat (QV-INT): answer immediately; the runtime closes stale transports itself.
          heartbeats += 1;
          send({ type: "pong" });
          voiceStatus.textContent = voice ? `${voiceStatus.textContent.replace(/ · ♥.*$/, "")} · ♥ ${heartbeats}` : voiceStatus.textContent;
          break;
        case "transcript": add(m.payload["role"] === "user" ? "user" : "agent", m.text ?? ""); break;
        case "audio_start": {
          lastResponseId = m.response_id ?? null;
          // F-13: one agent bubble per response, created now, filled/removed on audio_end (silent tool-only
          // responses produce no "(speaking…)" noise).
          const b = h("div", { class: "msg agent pending" }, m.text ? m.text : "…");
          if (m.response_id) agentBubbles.set(m.response_id, b);
          chat.append(b); chat.scrollTop = chat.scrollHeight;
          setStatus("agent speaking", "ok");
          // In voice mode the VoiceClient stamps playout_started when the first frame actually reaches the speaker.
          if (!voice) send({ type: "playout_started", response_id: m.response_id });
          break;
        }
        case "audio_end": {
          const b = m.response_id ? agentBubbles.get(m.response_id) : undefined;
          const audioMs = Number(m.payload?.["audio_ms"] ?? 0);
          if (b) {
            if (audioMs === 0 && !m.text) b.remove();
            else { b.classList.remove("pending"); b.textContent = m.text ?? `(spoke ${(audioMs / 1000).toFixed(1)} s — transcript off)`; }
            if (m.response_id) agentBubbles.delete(m.response_id);
          }
          setStatus("listening", "ok");
          if (!voice) send({ type: "playout_stopped", response_id: m.response_id });
          break;
        }
        case "stop_playout":
          add("sys", "⏹ you interrupted — agent stopped");
          if (m.response_id) agentBubbles.get(m.response_id)?.classList.add("cut");
          if (voice) voice.stopPlayout(); else send({ type: "playout_stopped", response_id: m.response_id });
          break;
        case "event": {
          const p = m.payload as { type?: string; payload?: Record<string, unknown> };
          if (p.type === "latency.sample" && p.payload?.["segment"] === "interruption") interruptionsPush(p.payload);
          break;
        }
        case "confirmation_request": {
          const row = h("div", { class: "msg sys" }, `Confirm: ${m.text ?? JSON.stringify(m.payload)} `,
            h("button", { onClick: () => { send({ type: "confirm", call_id: m.payload["call_id"], granted: true }); row.remove(); } }, "Yes"),
            h("button", { onClick: () => { send({ type: "confirm", call_id: m.payload["call_id"], granted: false }); row.remove(); } }, "No"));
          chat.append(row);
          break;
        }
        case "state": stateRedraw(m); break;
        case "error": {
          const code = String(m.payload["code"] ?? "");
          const row = h("div", { class: "msg sys bad" }, `⚠ ${explainError(code, String(m.text ?? ""))}`);
          if (code.startsWith("provider_credential") || code === "provider_failure") {
            row.append(" ", h("a", { href: "#/admin" }, "Open Admin →"));
          }
          chat.append(row);
          chat.scrollTop = chat.scrollHeight;
          break;
        }
        case "bye": add("sys", "agent closed the session"); break;
        default: break;
      }
    };
  };
  const doSend = () => { const t = input.value.trim(); if (!t) return; add("user", t); send({ type: "text", text: t }); input.value = ""; };
  input.addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") doSend(); });
  box.append(
    h("div", { class: "row" }, sel, compSel),
    h("div", { class: "row" },
      h("button", { class: "primary", onClick: connect }, "Connect"),
      h("button", { class: "danger", onClick: () => { send({ type: "bye" }); voice?.stopPlayout("hangup"); } }, "Hang up"),
      micBtn, meter, statusHost, voiceStatus),
    chat,
    h("div", { class: "row" }, input, h("button", { onClick: doSend }, "Send")),
  );
  return card;
}

function stateCard(): HTMLElement {
  const box = h("div", {}, h("p", { class: "muted" }, "Dialog / Activity state arrives on every `state` message."));
  stateRedraw = (m) => {
    clear(box);
    const entries = Object.entries(m.payload).flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, typeof v === "string" ? pill(v, toneFor(v)) : pre(v))]);
    box.append(h("dl", { class: "kv" }, ...entries));
  };
  return section("Session state", box);
}

function fmt(v: number | null | undefined): string { return v === null || v === undefined ? "—" : String(v); }

function interruptionsCard(): HTMLElement {
  const rows: InterruptionRecord[] = [];
  const box = h("div", {}, h("p", { class: "muted" }, "§31 watermarks per interruption (ms since session start): t0 speech onset · t1 barge-in · t2 cancel sent · t3 playout stopped · t4 reconciled."));
  const redraw = () => {
    clear(box);
    if (!rows.length) { box.append(h("p", { class: "muted" }, "No interruptions yet — speak (or type) while the agent is talking.")); return; }
    box.append(table(["response", "t0", "t1", "t2", "t3", "t4", "t1→t3", "t1→t4", "heard/unheard", "forced"], rows.map((r) => [
      h("code", {}, String(r.response_id).slice(0, 10)), fmt(r.t0), fmt(r.t1), fmt(r.t2), fmt(r.t3), fmt(r.t4),
      r.t1_to_t3_ms === null ? "—" : pill(`${r.t1_to_t3_ms} ms`, r.t1_to_t3_ms <= 300 ? "ok" : "warn"),
      r.t1_to_t4_ms === null ? "—" : pill(`${r.t1_to_t4_ms} ms`, r.t1_to_t4_ms <= 500 ? "ok" : "warn"),
      `${r.heard_len}/${r.unheard_len}`, r.forced ? pill("forced", "bad") : "no",
    ])));
  };
  interruptionsPush = (p) => {
    const t1 = Number(p["t1"]);
    const t3 = p["t3"] === null || p["t3"] === undefined ? null : Number(p["t3"]);
    const t4 = p["t4"] === null || p["t4"] === undefined ? null : Number(p["t4"]);
    rows.unshift({
      response_id: String(p["response_id"] ?? ""),
      t0: Number(p["t0"]), t1,
      t2: p["t2"] === null || p["t2"] === undefined ? null : Number(p["t2"]),
      t3, t4, forced: Boolean(p["forced"]),
      heard_len: Number(p["heard_len"] ?? 0), unheard_len: Number(p["unheard_len"] ?? 0),
      t1_to_t3_ms: t3 === null ? null : t3 - t1, t1_to_t4_ms: t4 === null ? null : t4 - t1,
    });
    redraw();
  };
  redraw();
  return section("Interruption metrics (QV-INT)", box);
}

function sessionsCard(): HTMLElement {
  const box = h("div");
  const card = section("Sessions & handoff queue", box);
  sessionsRedraw = async () => {
    clear(box);
    box.append(h("button", { onClick: () => void sessionsRedraw() }, "Refresh"));
    try {
      const rows = await api.sessions();
      box.append(table(["session", "activity", "composition", "channel", "running", "dialog", "activity state", "events", "close", "♥ hb", "outcome"], rows.map((s) => {
        const hb = (s["heartbeat"] ?? {}) as { sent?: number; last_rtt_ms?: number | null; dropped_audio_frames?: number };
        const code = s["close_code"] as number | null | undefined;
        return [
          h("code", {}, String(s.session_id).slice(0, 14)), String(s.activity_key),
          h("code", {}, String(s.composition_id ?? "")), String(s["channel"] ?? ""),
          s.running ? pill("live", "ok") : pill("ended", "muted"),
          String(s.dialog_state ?? ""), String(s.activity_state ?? ""), String(s.events),
          code === null || code === undefined ? "—" : pill(`${code}${s["close_reason"] ? " " + String(s["close_reason"]) : ""}`, code === 1000 ? "muted" : "bad"),
          hb.sent ? `${hb.sent}${hb.last_rtt_ms !== null && hb.last_rtt_ms !== undefined ? ` (${hb.last_rtt_ms} ms)` : ""}${hb.dropped_audio_frames ? ` · dropped ${hb.dropped_audio_frames}` : ""}` : "—",
          s.outcome ? pill(String((s.outcome as { primary?: string }).primary ?? "?"), "info") : "—",
        ];
      })));
      if (currentSid) {
        const d = (await api.session(currentSid)) as { outcome?: unknown };
        if (d.outcome) box.append(h("h3", {}, "Outcome of current session"), pre(d.outcome));
      }
    } catch (e) { box.append(h("p", { class: "muted" }, errMsg(e))); }
  };
  void sessionsRedraw();
  return card;
}

function eventsCard(): HTMLElement {
  const list = h("div", { class: "events" });
  eventsPush = (m) => {
    const ev = m.type === "event" ? (m.payload as { type?: string; seq?: number; payload?: unknown }) : { type: `transport:${m.type}`, payload: m.payload };
    list.prepend(h("div", {}, `${ev.seq ?? ""} ${ev.type ?? ""} ${ev.payload ? JSON.stringify(ev.payload) : ""}`.slice(0, 220)));
    while (list.children.length > 300) list.lastChild?.remove();
  };
  const load = async () => {
    clear(list);
    try {
      const evs = await api.events(0, 200);
      for (const e of evs) list.prepend(h("div", {}, `${e.seq} ${e.type} ${JSON.stringify(e.payload)}`.slice(0, 220)));
    } catch (e) { toast(errMsg(e), "bad"); }
  };
  return section("Event stream (qevion.event.v1, filtered)", h("div", { class: "row" }, h("button", { onClick: () => void load() }, "Load global log")), list);
}
