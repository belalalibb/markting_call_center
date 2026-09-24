// Tiny DOM helpers (no framework). Everything is escaped by default.

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | boolean | ((e: Event) => void)> = {},
  ...children: (Node | string | null | undefined | false)[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (typeof v === "function") el.addEventListener(k.replace(/^on/, "").toLowerCase(), v);
    else if (typeof v === "boolean") {
      if (v) el.setAttribute(k, "");
    } else el.setAttribute(k, v);
  }
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue;
    el.append(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return el;
}

export function clear(el: Element): void {
  while (el.firstChild) el.removeChild(el.firstChild);
}

export function pill(text: string, tone: "ok" | "warn" | "bad" | "info" | "muted" = "info"): HTMLElement {
  return h("span", { class: `pill ${tone}` }, text);
}

export function toneFor(state: string): "ok" | "warn" | "bad" | "info" | "muted" {
  const s = state.toUpperCase();
  if (s.includes("READY") || s === "ACTIVE" || s === "SUPPORTED" || s === "APPROVED" || s === "REVIEW") return "ok";
  if (s.includes("BLOCK") || s === "UNSUPPORTED" || s === "FAILED" || s === "RETIRED") return "bad";
  if (s.includes("NEEDS") || s.includes("REQUIRES") || s.includes("UNVERIFIED") || s === "WARN" || s === "ASKING") return "warn";
  if (s === "DRAFT" || s === "INFO") return "muted";
  return "info";
}

export function pre(obj: unknown): HTMLElement {
  return h("pre", { class: "code" }, typeof obj === "string" ? obj : JSON.stringify(obj, null, 2));
}

export function section(title: string, ...children: (Node | string | null | undefined | false)[]): HTMLElement {
  return h("section", { class: "card" }, h("h2", {}, title), ...children);
}

export function table(headers: string[], rows: (Node | string)[][]): HTMLElement {
  // wrapped so wide tables scroll inside their card instead of widening the page (P4 mobile)
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      {},
      h("thead", {}, h("tr", {}, ...headers.map((x) => h("th", {}, x)))),
      h("tbody", {}, ...rows.map((r) => h("tr", {}, ...r.map((c) => h("td", {}, c))))),
    ),
  );
}

export function toast(msg: string, tone: "ok" | "bad" | "info" = "info"): void {
  const t = h("div", { class: `toast ${tone}` }, msg);
  document.body.append(t);
  setTimeout(() => t.remove(), 4000);
}

export function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
