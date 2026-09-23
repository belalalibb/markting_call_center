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

async function route(): Promise<void> {
  const mode = (location.hash.replace(/^#\/?/, "") || "config").split("/")[0] ?? "config";
  const fn = modes[mode] ?? renderConfig;
  document.querySelectorAll<HTMLAnchorElement>("nav a").forEach((a) => a.classList.toggle("active", a.dataset["mode"] === mode));
  const root = document.getElementById("app")!;
  clear(root);
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
    next = pill(`ok · default ${runtimeSummary.composition} · ${runtimeSummary.activities} activities · ${runtimeSummary.sessions_live} live`, "ok");
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

window.addEventListener("hashchange", () => void route());
void route();
void health();
setInterval(() => void health(), 10_000);
