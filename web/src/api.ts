// Thin typed client for the QEVION runtime REST surface. No business logic here.

export type Json = Record<string, unknown>;

async function req<T = Json>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (form) init.body = form;
  else if (body !== undefined) {
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const r = await fetch(path, init);
  const text = await r.text();
  let data: unknown = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* non-json */
  }
  if (!r.ok) {
    const detail = (data as { detail?: unknown })?.detail ?? data;
    throw new ApiError(r.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data as T;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export interface ActivitySummary {
  key: string;
  activity_id: string;
  version: string;
  tenant_id: string;
  name: string;
  direction: string;
  channels: string[];
  readiness: string;
  preflight: { status: string; blocking: number; total: number } | null;
  decisions_unapproved: number;
  notes: string[];
}

export interface Question {
  question_id: string;
  kind: string;
  priority: number;
  text: string;
  why_it_matters: string;
  target_path: string;
  answer_type: string;
  options: string[];
  proposed_default: unknown;
  source_refs: string[];
  blocking: boolean;
}

export interface CopilotView {
  config_session_id: string;
  tenant_id: string;
  activity_id: string;
  status: string;
  readiness_state: string;
  draft_valid: boolean;
  validation_errors: string[];
  draft: Json;
  decisions: { item_path: string; proposed_by: string; approved_by: string | null }[];
  unapproved: string[];
  questions: Question[];
  questions_total: number;
  blocking_total: number;
  gap_counts: Record<string, number>;
  contradictions: Json[];
  capability_requirements: { requirement: string; required_capability: string; action: string; integration: string }[];
  preflight_findings: { reason: string; path: string; message: string; severity: string; fix_hint: string | null }[];
  readiness_findings: { category: string; description: string; severity: string; mitigation: string | null }[];
  simulation_cases: string[];
  explanation: string;
  question_explanations: Record<string, string>;
}

export interface CompositionSummary {
  composition_id: string;
  name?: string;
  s2s_adapter?: string;
  turn_adapter?: string;
  decision_adapter?: string;
  credential_source?: string | null;
  [k: string]: unknown;
}

export interface InterruptionRecord {
  response_id: string;
  t0: number; t1: number; t2: number | null; t3: number | null; t4: number | null;
  forced: boolean; heard_len: number; unheard_len: number;
  t1_to_t3_ms: number | null; t1_to_t4_ms: number | null;
}

export const api = {
  health: () => req("GET", "/api/health"),
  compositions: () => req<CompositionSummary[]>("GET", "/api/compositions"),
  tenants: () => req<Json[]>("GET", "/api/tenants"),
  createTenant: (body: Json) => req("POST", "/api/tenants", body),
  activities: () => req<ActivitySummary[]>("GET", "/api/activities"),
  activity: (key: string) => req("GET", `/api/activities/${encodeURIComponent(key)}`),
  uploadActivityYaml: (file: File) => {
    const f = new FormData();
    f.append("file", file);
    return req<ActivitySummary>("POST", "/api/activities/yaml", undefined, f);
  },
  preflight: (key: string, strict = false) =>
    req("POST", `/api/activities/${encodeURIComponent(key)}/preflight?strict=${strict}`),
  capabilities: (key: string) => req("POST", `/api/activities/${encodeURIComponent(key)}/capabilities`),
  transition: (key: string, to: string, reason = "operator") =>
    req("POST", `/api/activities/${encodeURIComponent(key)}/transition`, { to, reason, actor: "operator:web" }),
  registry: () => req("GET", "/api/registry"),
  uploadKnowledge: (tenantId: string, file: File, activityKey?: string, priority = 100) => {
    const f = new FormData();
    f.append("tenant_id", tenantId);
    f.append("file", file);
    if (activityKey) f.append("activity_key", activityKey);
    f.append("priority", String(priority));
    return req("POST", "/api/knowledge/upload", undefined, f);
  },
  conflicts: (tenantId: string) => req<Json[]>("GET", `/api/knowledge/${encodeURIComponent(tenantId)}/conflicts`),
  facts: (tenantId: string, approved = true) =>
    req<Json[]>("GET", `/api/knowledge/${encodeURIComponent(tenantId)}/facts?approved=${approved}`),
  resolve: (cid: string, winner: string) =>
    req("POST", `/api/knowledge/contradictions/${encodeURIComponent(cid)}/resolve?winner=${encodeURIComponent(winner)}&by=operator:web`),
  approveFact: (fid: string) => req("POST", `/api/knowledge/facts/${encodeURIComponent(fid)}/approve?by=operator:web`),
  credStatus: (provider: string) => req("GET", `/api/admin/credentials/${encodeURIComponent(provider)}`),
  setTestKey: (provider: string, value: string, ttl: number) =>
    req("POST", "/api/admin/test-key", { provider, value, ttl_seconds: ttl }),
  clearTestKey: (provider: string) => req("DELETE", `/api/admin/test-key?provider=${encodeURIComponent(provider)}`),
  sessions: () => req<Json[]>("GET", "/api/sessions"),
  session: (sid: string) => req("GET", `/api/sessions/${encodeURIComponent(sid)}`),
  events: (since = 0, limit = 200) => req<Json[]>("GET", `/api/events?since=${since}&limit=${limit}`),
  // copilot
  copilotStart: (body: Json) => req<CopilotView>("POST", "/api/copilot/sessions", body),
  copilotSessions: () => req<Json[]>("GET", "/api/copilot/sessions"),
  copilotView: (sid: string, limit = 3) => req<CopilotView>("GET", `/api/copilot/sessions/${sid}?limit=${limit}`),
  copilotAnswer: (sid: string, question_id: string, value: unknown, mode: "answer" | "accept" | "defer" = "answer") =>
    req<CopilotView>("POST", `/api/copilot/sessions/${sid}/answer`, { question_id, value, mode, operator_id: "operator:web" }),
  copilotApprove: (sid: string, item_path: string) =>
    req<CopilotView>("POST", `/api/copilot/sessions/${sid}/approve`, { item_path, operator_id: "operator:web" }),
  copilotPublish: (sid: string) => req("POST", `/api/copilot/sessions/${sid}/publish`),
};

export function wsUrl(activityKey: string, channel = "text", composition?: string): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const comp = composition ? `&composition=${encodeURIComponent(composition)}` : "";
  return `${proto}//${location.host}/ws/sessions/${encodeURIComponent(activityKey)}?channel=${channel}${comp}`;
}
