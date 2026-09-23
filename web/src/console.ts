// Operator Console: live chat session over WS (mock composition), state, events, handoffs.
import { api, wsUrl, type ActivitySummary } from "./api";
import { clear, errMsg, h, pill, pre, section, table, toast, toneFor } from "./ui";

interface ServerMsg {
  type: string;
  session_id: string;
  response_id?: string | null;
  text?: string | null;
  payload: Record<string, unknown>;
}

let ws: WebSocket | null = null;
let currentSid: string | null = null;

let stateRedraw: (m: ServerMsg) => void = () => {};
let sessionsRedraw: () => Promise<void> = async () => {};
let eventsPush: (m: ServerMsg) => void = () => {};

export async function renderConsole(root: HTMLElement): Promise<void> {
  root.className = "";
  clear(root);
  const activities = await api.activities().catch(() => [] as ActivitySummary[]);
  root.append(chatCard(activities), stateCard(), sessionsCard(), eventsCard());
}

function chatCard(activities: ActivitySummary[]): HTMLElement {
  const box = h("div");
  const card = section("Live session (text channel, mock provider)", box);
  const sel = h("select", {}, ...activities.map((a) => h("option", { value: a.key }, `${a.key} — ${a.name} [${a.readiness}]`)));
  const chat = h("div", { class: "chat" });
  const input = h("input", { placeholder: "type as the caller… (try a question, field values, or 'stop')" });
  const statusHost = h("span");
  const setStatus = (t: string, tone: "ok" | "muted" | "bad") => { clear(statusHost); statusHost.append(pill(t, tone)); };
  setStatus("disconnected", "muted");
  const add = (cls: string, text: string) => { chat.append(h("div", { class: `msg ${cls}` }, text)); chat.scrollTop = chat.scrollHeight; };
  const send = (obj: Record<string, unknown>) => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ schema: "qevion.transport.v1", client_ts_ms: Date.now(), ...obj }));
  };
  const connect = () => {
    ws?.close();
    clear(chat);
    ws = new WebSocket(wsUrl(sel.value, "text"));
    ws.binaryType = "arraybuffer";
    ws.onopen = () => { setStatus("connected", "ok"); add("sys", `connected → ${sel.value}`); send({ type: "hello" }); };
    ws.onclose = (e) => { setStatus("disconnected", "muted"); add("sys", `closed (${e.code}${e.reason ? ": " + e.reason : ""})`); void sessionsRedraw(); };
    ws.onerror = () => { setStatus("error", "bad"); add("sys", "socket error"); };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") { add("sys", `◼ audio ${(ev.data as ArrayBuffer).byteLength} bytes`); return; }
      const m = JSON.parse(ev.data) as ServerMsg;
      currentSid = m.session_id;
      eventsPush(m);
      switch (m.type) {
        case "ready": add("sys", "session ready"); break;
        case "transcript": add(m.payload["role"] === "user" ? "user" : "agent", m.text ?? ""); break;
        case "audio_start": add("agent", m.text ? m.text : "(speaking…)"); send({ type: "playout_started", response_id: m.response_id }); break;
        case "audio_end": send({ type: "playout_stopped", response_id: m.response_id }); break;
        case "stop_playout": add("sys", "⏹ interrupted — playout stopped"); break;
        case "confirmation_request": {
          const row = h("div", { class: "msg sys" }, `Confirm: ${m.text ?? JSON.stringify(m.payload)} `,
            h("button", { onClick: () => { send({ type: "confirm", call_id: m.payload["call_id"], granted: true }); row.remove(); } }, "Yes"),
            h("button", { onClick: () => { send({ type: "confirm", call_id: m.payload["call_id"], granted: false }); row.remove(); } }, "No"));
          chat.append(row);
          break;
        }
        case "state": stateRedraw(m); break;
        case "event": break;
        case "error": add("sys", `error: ${m.text}`); break;
        case "bye": add("sys", "agent closed the session"); break;
        default: break;
      }
    };
  };
  const doSend = () => { const t = input.value.trim(); if (!t) return; add("user", t); send({ type: "text", text: t }); input.value = ""; };
  input.addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") doSend(); });
  box.append(
    h("div", { class: "row" }, sel, h("button", { class: "primary", onClick: connect }, "Connect"), h("button", { class: "danger", onClick: () => send({ type: "bye" }) }, "Hang up"), statusHost),
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

function sessionsCard(): HTMLElement {
  const box = h("div");
  const card = section("Sessions & handoff queue", box);
  sessionsRedraw = async () => {
    clear(box);
    box.append(h("button", { onClick: () => void sessionsRedraw() }, "Refresh"));
    try {
      const rows = await api.sessions();
      box.append(table(["session", "activity", "running", "dialog", "activity state", "events", "handoffs", "outcome"], rows.map((s) => [
        h("code", {}, String(s.session_id).slice(0, 14)), String(s.activity_key), s.running ? pill("live", "ok") : pill("ended", "muted"),
        String(s.dialog_state ?? ""), String(s.activity_state ?? ""), String(s.events), s.handoffs ? pill(String(s.handoffs), "warn") : "0",
        s.outcome ? pill(String((s.outcome as { primary?: string }).primary ?? "?"), "info") : "—",
      ])));
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
