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

async function health(): Promise<void> {
  const el = document.getElementById("health")!;
  try {
    const hres = (await api.health()) as { composition: string; activities: number; sessions_live: number };
    clear(el);
    el.replaceWith(pill(`ok · ${hres.composition} · ${hres.activities} activities · ${hres.sessions_live} live`, "ok"));
    document.querySelector("#top .pill")!.id = "health";
  } catch {
    clear(el);
    el.replaceWith(pill("runtime unreachable", "bad"));
    document.querySelector("#top .pill")!.id = "health";
  }
}

window.addEventListener("hashchange", () => void route());
void route();
void health();
setInterval(() => void health(), 10_000);
