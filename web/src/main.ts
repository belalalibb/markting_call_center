// Router + health pill. Three modes share one app; no framework.
import { renderAdmin } from "./admin";
import { api } from "./api";
import { renderConfig } from "./config";
import { renderConsole } from "./console";
import { clear, h, pill } from "./ui";

const modes: Record<string, (root: HTMLElement) => Promise<void>> = {
  config: renderConfig,
  console: renderConsole,
  admin: renderAdmin,
};

/** Operator login (F-07). Shown when the runtime has QEVION_ADMIN_TOKEN set and this browser has no session. */
function renderLogin(root: HTMLElement): void {
  clear(root);
  const input = h("input", { type: "password", placeholder: "operator token (QEVION_ADMIN_TOKEN)", autocomplete: "current-password" });
  const msg = h("p", { class: "muted" }, "This QEVION runtime is protected. Enter the operator token set on the server.");
  const submit = async () => {
    try {
      await api.login(input.value);
      input.value = "";
      await route();
      void health();
    } catch {
      msg.textContent = "Invalid token — check QEVION_ADMIN_TOKEN on the server.";
    }
  };
  input.addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") void submit(); });
  root.append(h("section", { class: "card" }, h("h2", {}, "Sign in"), msg,
    h("div", { class: "row" }, input, h("button", { class: "primary", onClick: () => void submit() }, "Sign in"))));
}

/** P4 Normal/Advanced: advanced-only elements carry `.advanced` and are hidden by `body.normal`. */
const UI_MODE_KEY = "qevion.uiMode";
function applyUiMode(mode: "normal" | "advanced"): void {
  document.body.classList.toggle("normal", mode === "normal");
  localStorage.setItem(UI_MODE_KEY, mode);
  const btn = document.getElementById("uimode");
  if (btn) btn.textContent = mode === "normal" ? "Normal view" : "Advanced view";
}
function initUiMode(): void {
  const btn = h("button", { id: "uimode", class: "ghost", title: "Normal hides engineering telemetry" }, "");
  btn.addEventListener("click", () => applyUiMode(document.body.classList.contains("normal") ? "advanced" : "normal"));
  document.getElementById("health")?.before(btn);
  applyUiMode((localStorage.getItem(UI_MODE_KEY) as "normal" | "advanced" | null) ?? "normal");
}

/** P4 first-run: tells a new operator the 3 steps, and whether a real provider key is present yet. */
async function firstRunBanner(): Promise<HTMLElement | null> {
  if (localStorage.getItem("qevion.firstRunDone") === "1") return null;
  let comps: { simulated?: boolean; ready?: boolean }[] = [];
  try { comps = await api.compositions(); } catch { return null; }
  const realReady = comps.some((c) => !c.simulated && c.ready);
  const b = h("div", { class: "banner info", id: "firstrun" },
    h("strong", {}, "Getting started: "),
    "1) Config Center — pick or create an activity. ",
    "2) ", realReady ? "A real provider key is present. " : h("a", { href: "#/admin" }, "Admin → paste your OpenAI key"),
    realReady ? "" : " (until then, only the simulated mock composition works). ",
    "3) Operator Console — choose a composition, Connect, then Mic. ",
    h("button", { class: "ghost", onClick: () => { localStorage.setItem("qevion.firstRunDone", "1"); b.remove(); } }, "Dismiss"));
  return b;
}

function devModeBanner(): HTMLElement {
  return h("div", { class: "banner warn" },
    "Development mode: no operator token is set, so anyone who can reach this URL can use it (and your provider key). ",
    "Set QEVION_ADMIN_TOKEN on the server before sharing the link.");
}

async function route(): Promise<void> {
  const mode = (location.hash.replace(/^#\/?/, "") || "config").split("/")[0] ?? "config";
  const fn = modes[mode] ?? renderConfig;
  document.querySelectorAll<HTMLAnchorElement>("nav a").forEach((a) => a.classList.toggle("active", a.dataset["mode"] === mode));
  const root = document.getElementById("app")!;
  clear(root);
  let auth: { auth: string; authorized: boolean } = { auth: "disabled", authorized: true };
  try { auth = await api.authStatus(); } catch { /* older runtime: no auth endpoint */ }
  if (!auth.authorized) { renderLogin(root); return; }
  document.getElementById("devbanner")?.remove();
  if (auth.auth === "disabled") {
    const b = devModeBanner();
    b.id = "devbanner";
    document.getElementById("top")?.after(b);
  }
  if (!document.getElementById("firstrun")) {
    const fr = await firstRunBanner();
    if (fr) (document.getElementById("devbanner") ?? document.getElementById("top"))?.after(fr);
  }
  root.append(h("p", { class: "muted" }, "loading…"));
  try {
    await fn(root);
  } catch (e) {
    clear(root);
    root.append(h("section", { class: "card" }, h("h2", {}, "error"), h("pre", { class: "code" }, e instanceof Error ? e.message : String(e))));
  }
}

/** Header pill. Runtime default composition is only shown while *no* session is connected; once the console
 *  connects, the pill mirrors the actual session (`ready` payload: composition/channel/provider) so the header
 *  can never disagree with the live status line. */
let liveHeader: { composition: string; channel: string; provider: string; hb?: string } | null = null;
let runtimeSummary: { composition: string; activities: number; sessions_live: number } | null = null;

function renderHealth(): void {
  const el = document.getElementById("health")!;
  let next: HTMLElement;
  if (liveHeader) {
    next = pill(
      `live · ${liveHeader.composition} · ${liveHeader.channel} · ${liveHeader.provider}${liveHeader.hb ? ` · ♥ ${liveHeader.hb}` : ""}`,
      "ok",
    );
  } else if (runtimeSummary) {
    const sim = runtimeSummary.composition.includes("mock") ? " (simulated)" : "";
    next = pill(`ok · default ${runtimeSummary.composition}${sim} · ${runtimeSummary.activities} activities · ${runtimeSummary.sessions_live} live`, "ok");
  } else {
    next = pill("runtime unreachable", "bad");
  }
  next.id = "health";
  el.replaceWith(next);
}

async function health(): Promise<void> {
  try {
    runtimeSummary = (await api.health()) as { composition: string; activities: number; sessions_live: number };
  } catch {
    runtimeSummary = null;
  }
  renderHealth();
}

window.addEventListener("qevion:live", (e) => {
  liveHeader = (e as CustomEvent<typeof liveHeader>).detail;
  renderHealth();
});

window.addEventListener("qevion:unauthorized", () => renderLogin(document.getElementById("app")!));
window.addEventListener("hashchange", () => void route());
initUiMode();
void route();
void health();
setInterval(() => void health(), 10_000);
