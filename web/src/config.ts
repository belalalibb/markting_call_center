// Config Center: Copilot session (questions → answers → proposal → publish), activities, knowledge.
import { api, type ActivitySummary, type CopilotView, type Question } from "./api";
import { clear, errMsg, h, pill, pre, section, table, toast, toneFor } from "./ui";

interface State {
  sid: string | null;
  view: CopilotView | null;
  activities: ActivitySummary[];
  selected: string | null;
  detail: unknown;
  tenant: string;
}

const st: State = { sid: null, view: null, activities: [], selected: null, detail: null, tenant: "t_demo" };

export async function renderConfig(root: HTMLElement): Promise<void> {
  root.className = "";
  clear(root);
  st.activities = await api.activities().catch(() => []);
  root.append(copilotCard(), activitiesCard(), knowledgeCard(), proposalCard());
}

// ------------------------------------------------------------------ copilot
function copilotCard(): HTMLElement {
  const box = h("div");
  const card = section("Configuration Copilot", box);
  const draw = () => {
    clear(box);
    if (!st.view) {
      const tenant = h("input", { value: st.tenant, placeholder: "tenant_id" });
      const actId = h("input", { value: "act_new", placeholder: "activity_id" });
      const name = h("input", { value: "New Activity", placeholder: "name" });
      const seedSel = h("select", {}, h("option", { value: "" }, "start from scratch"));
      for (const a of st.activities) seedSel.append(h("option", { value: a.key }, `seed from ${a.key}`));
      box.append(
        h("p", { class: "muted" }, "The Copilot asks only what the current state cannot answer. No fixed questionnaire; business decisions are never guessed."),
        h("div", { class: "row" }, tenant, actId, name),
        h("div", { class: "row" }, seedSel, h("button", { class: "primary", onClick: async () => {
          try {
            let seed: unknown = undefined;
            if (seedSel.value) {
              const d = (await api.activity(seedSel.value)) as { blueprint: Record<string, unknown> };
              seed = d.blueprint;
            }
            st.tenant = tenant.value;
            st.view = await api.copilotStart({ tenant_id: tenant.value, activity_id: actId.value, name: name.value, seed, operator_id: "operator:web" });
            st.sid = st.view.config_session_id;
            draw();
            redrawProposal();
          } catch (e) { toast(errMsg(e), "bad"); }
        } }, "Start session")),
      );
      return;
    }
    const v = st.view;
    box.append(
      h("div", { class: "row" },
        pill(`status: ${v.status}`, toneFor(v.status)),
        pill(`readiness: ${v.readiness_state}`, toneFor(v.readiness_state)),
        pill(v.draft_valid ? "draft valid" : "draft incomplete", v.draft_valid ? "ok" : "warn"),
        pill(`${v.blocking_total} blocking / ${v.questions_total} open`, v.blocking_total ? "bad" : "ok"),
        h("button", { onClick: () => { st.view = null; st.sid = null; draw(); redrawProposal(); } }, "New session"),
      ),
    );
    if (v.questions.length === 0) {
      box.append(h("p", { class: "muted" }, v.status === "review" ? "Nothing left to ask — review the proposal and publish." : "No open questions."));
    }
    for (const q of v.questions) box.append(questionEl(q, v));
    if (v.unapproved.length) {
      box.append(h("h3", {}, "Decisions awaiting your approval"));
      for (const p of v.unapproved) box.append(h("div", { class: "row" }, h("code", {}, p), h("button", { onClick: () => act(() => api.copilotApprove(st.sid!, p)) }, "Approve")));
    }
    box.append(h("div", { class: "row" },
      h("button", { class: "primary", onClick: async () => {
        try {
          const r = (await api.copilotPublish(st.sid!)) as { activity_key: string };
          toast(`Published ${r.activity_key}`, "ok");
          st.activities = await api.activities();
          const main = document.getElementById("app")!;
          await renderConfig(main);
        } catch (e) { toast(errMsg(e), "bad"); }
      } }, "Publish as Activity version"),
    ));
  };
  draw();
  (card as HTMLElement & { redraw?: () => void }).redraw = draw;
  copilotRedraw = draw;
  return card;
}

let copilotRedraw: () => void = () => {};
let proposalRedraw: () => void = () => {};
function redrawProposal(): void { proposalRedraw(); }

async function act(fn: () => Promise<CopilotView>): Promise<void> {
  try {
    st.view = await fn();
    copilotRedraw();
    redrawProposal();
  } catch (e) { toast(errMsg(e), "bad"); }
}

function questionEl(q: Question, v: CopilotView): HTMLElement {
  const el = h("div", { class: `q ${q.blocking ? "blocking" : ""}` });
  el.append(
    h("div", { class: "row" }, pill(q.kind.replace("_", " "), q.blocking ? "bad" : toneFor(q.kind)), q.blocking ? pill("blocking", "bad") : pill("optional", "muted")),
    h("div", {}, h("strong", {}, q.text)),
    h("div", { class: "why" }, "Why: ", q.why_it_matters),
    h("div", { class: "path" }, "→ ", q.target_path, q.source_refs.length ? `  (from: ${q.source_refs.join(", ")})` : ""),
  );
  const sid = st.sid!;
  let input: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
  if (q.answer_type === "choice" && q.options.length) {
    input = h("select", {}, ...q.options.map((o) => h("option", { value: o }, o)));
    if (typeof q.proposed_default === "string") (input as HTMLSelectElement).value = q.proposed_default;
  } else if (q.answer_type === "yes_no") {
    input = h("select", {}, h("option", { value: "yes" }, "yes"), h("option", { value: "no" }, "no"));
  } else if (q.answer_type === "number") {
    input = h("input", { type: "number" });
  } else if (q.answer_type === "upload") {
    input = h("input", { placeholder: "source id(s) already uploaded, comma-separated — or upload in Knowledge panel" });
  } else {
    input = h("textarea", { placeholder: q.answer_type === "confirm_proposal" ? "edit list (comma-separated) or accept the proposal" : "your answer (comma-separate lists)" });
  }
  const row = h("div", { class: "row" }, input,
    h("button", { class: "primary", onClick: () => act(() => api.copilotAnswer(sid, q.question_id, parse(input.value, q), "answer")) }, "Answer"),
  );
  if (q.proposed_default !== null && q.proposed_default !== undefined) {
    row.append(h("button", { onClick: () => act(() => api.copilotAnswer(sid, q.question_id, null, "accept")) }, `Accept proposal (${JSON.stringify(q.proposed_default)})`));
  }
  if (!q.blocking) row.append(h("button", { onClick: () => act(() => api.copilotAnswer(sid, q.question_id, null, "defer")) }, "Defer"));
  el.append(row);
  const expl = v.question_explanations[q.question_id];
  if (expl) el.append(h("details", {}, h("summary", { class: "muted" }, "explain"), pre(expl)));
  return el;
}

function parse(raw: string, q: Question): unknown {
  const s = raw.trim();
  if (q.answer_type === "number") return Number(s);
  if (q.answer_type === "yes_no") return s === "yes";
  if (["channels", "data.required", "outcome_schema.primary", "completion.success_rules", "knowledge.sources", "handoff_rules", "coverage.objections"].includes(q.target_path) || q.answer_type === "confirm_proposal" || q.answer_type === "upload") {
    return s.split(/[,\n;]+/).map((x) => x.trim()).filter(Boolean);
  }
  return s;
}

// ----------------------------------------------------------------- proposal
function proposalCard(): HTMLElement {
  const box = h("div");
  const card = section("Proposal (machine-readable) & Explanation (human)", box);
  card.classList.add("span2");
  proposalRedraw = () => {
    clear(box);
    const v = st.view;
    if (!v) { box.append(h("p", { class: "muted" }, "Start a Copilot session to see the proposal.")); return; }
    const left = h("div");
    left.append(h("h3", {}, "Explanation"), pre(v.explanation));
    if (v.readiness_findings.length) {
      left.append(h("h3", {}, "What could go wrong"), table(["sev", "category", "description", "mitigation"], v.readiness_findings.map((r) => [pill(r.severity, toneFor(r.severity)), r.category, r.description, r.mitigation ?? ""])));
    }
    if (v.preflight_findings.length) {
      left.append(h("h3", {}, "Preflight findings"), table(["sev", "reason", "path", "fix"], v.preflight_findings.map((f) => [pill(f.severity, toneFor(f.severity)), f.reason, h("code", {}, f.path), f.fix_hint ?? f.message])));
    }
    if (v.capability_requirements.length) {
      left.append(h("h3", {}, "Capability mapping"), table(["requirement", "capability", "action", "integration"], v.capability_requirements.map((c) => [c.requirement, h("code", {}, c.required_capability), pill(c.action, toneFor(c.action)), c.integration])));
    }
    const right = h("div");
    right.append(h("h3", {}, "Decisions"), table(["path", "proposed by", "approved by"], v.decisions.map((d) => [h("code", {}, d.item_path), d.proposed_by, d.approved_by ? pill(d.approved_by, "ok") : pill("unapproved", "warn")])));
    right.append(h("h3", {}, "Simulation cases (P5)"), h("div", {}, ...v.simulation_cases.map((c) => pill(c, "muted"))));
    if (!v.draft_valid) right.append(h("h3", {}, "Validation errors"), pre(v.validation_errors.join("\n")));
    right.append(h("details", {}, h("summary", {}, "Draft blueprint (JSON)"), pre(v.draft)));
    box.append(h("div", { style: "display:grid;grid-template-columns:1fr 1fr;gap:16px" }, left, right));
  };
  proposalRedraw();
  return card;
}

// --------------------------------------------------------------- activities
function activitiesCard(): HTMLElement {
  const box = h("div");
  const card = section("Activities & Readiness", box);
  const draw = async () => {
    clear(box);
    const file = h("input", { type: "file", accept: ".yaml,.yml" });
    box.append(h("div", { class: "row" }, file, h("button", { onClick: async () => {
      const f = file.files?.[0]; if (!f) return;
      try { await api.uploadActivityYaml(f); st.activities = await api.activities(); toast("Blueprint uploaded", "ok"); await draw(); } catch (e) { toast(errMsg(e), "bad"); }
    } }, "Upload Blueprint YAML")));
    const rows = st.activities.map((a) => {
      const tr = h("tr", { "data-key": a.key, onClick: async () => { st.selected = a.key; st.detail = await api.activity(a.key); await draw(); } },
        h("td", {}, h("code", {}, a.key)), h("td", {}, a.name), h("td", {}, a.direction), h("td", {}, pill(a.readiness, toneFor(a.readiness))),
        h("td", {}, a.preflight ? pill(`${a.preflight.status} (${a.preflight.blocking} block)`, a.preflight.status === "READY" ? "ok" : "bad") : pill("not run", "muted")),
        h("td", {}, a.decisions_unapproved ? pill(`${a.decisions_unapproved} unapproved`, "warn") : pill("approved", "ok")));
      if (a.key === st.selected) tr.classList.add("sel");
      return tr;
    });
    box.append(h("table", {}, h("thead", {}, h("tr", {}, ...["key", "name", "dir", "readiness", "preflight", "decisions"].map((x) => h("th", {}, x)))), h("tbody", {}, ...rows)));
    if (st.selected) {
      const key = st.selected;
      const trans = h("select", {}, ...["DISCOVERY_IN_PROGRESS", "NEEDS_INFORMATION", "NEEDS_CONFIGURATION", "READY_FOR_SIMULATION", "READY_FOR_ACTIVATION", "SUSPENDED", "RETIRED"].map((s) => h("option", { value: s }, s)));
      box.append(h("div", { class: "row" },
        h("button", { class: "primary", onClick: () => run(() => api.preflight(key, false)) }, "Run preflight"),
        h("button", { onClick: () => run(() => api.preflight(key, true)) }, "Preflight (strict)"),
        h("button", { onClick: () => run(() => api.capabilities(key)) }, "Map capabilities"),
        trans, h("button", { onClick: () => run(() => api.transition(key, trans.value)) }, "Transition"),
      ));
      if (st.detail) box.append(h("details", { open: true }, h("summary", {}, "Last result"), pre(st.detail)));
    }
  };
  const run = async (fn: () => Promise<unknown>) => {
    try { st.detail = await fn(); st.activities = await api.activities(); toast("done", "ok"); await draw(); } catch (e) { toast(errMsg(e), "bad"); }
  };
  void draw();
  return card;
}

// ---------------------------------------------------------------- knowledge
function knowledgeCard(): HTMLElement {
  const box = h("div");
  const card = section("Knowledge (upload → report → conflicts)", box);
  let report: unknown = null;
  const draw = async () => {
    clear(box);
    const tenant = h("input", { value: st.tenant, placeholder: "tenant_id" });
    const file = h("input", { type: "file", accept: ".csv,.json,.yaml,.yml,.txt,.md" });
    const act = h("select", {}, h("option", { value: "" }, "(no activity: skip gap analysis)"));
    for (const a of st.activities) act.append(h("option", { value: a.key }, a.key));
    const prio = h("input", { type: "number", value: "100", title: "priority (lower wins conflicts)" });
    box.append(h("div", { class: "row" }, tenant, act), h("div", { class: "row" }, file, prio, h("button", { class: "primary", onClick: async () => {
      const f = file.files?.[0]; if (!f) return;
      try { st.tenant = tenant.value; report = await api.uploadKnowledge(tenant.value, f, act.value || undefined, Number(prio.value)); toast("Ingested", "ok"); await draw(); } catch (e) { toast(errMsg(e), "bad"); }
    } }, "Upload")));
    const conflicts = await api.conflicts(tenant.value).catch(() => []);
    if (conflicts.length) {
      box.append(h("h3", {}, `${conflicts.length} unresolved contradiction(s)`));
      for (const c of conflicts) {
        const facts = c.fact_ids as string[];
        const sel = h("select", {}, ...facts.map((f) => h("option", { value: f }, f)));
        box.append(h("div", { class: "row" }, h("span", {}, String(c.description)), sel, h("button", { onClick: async () => { try { await api.resolve(String(c.contradiction_id), sel.value); toast("resolved", "ok"); await draw(); } catch (e) { toast(errMsg(e), "bad"); } } }, "Resolve")));
      }
    }
    if (report) {
      const r = report as { summary: Record<string, number>; gaps: { gap_class: string; question_for_operator: string }[]; injection_flags: unknown[]; warnings: string[] };
      box.append(h("h3", {}, "Ingestion report"), h("div", {}, ...Object.entries(r.summary).map(([k, v]) => pill(`${k}: ${v}`, "muted"))));
      if (r.injection_flags.length) box.append(pill(`${r.injection_flags.length} injection flag(s)`, "bad"));
      if (r.gaps.length) box.append(table(["class", "question for operator"], r.gaps.map((g) => [pill(g.gap_class, toneFor(g.gap_class)), g.question_for_operator])));
      box.append(h("details", {}, h("summary", {}, "full report"), pre(report)));
    }
  };
  void draw();
  return card;
}
