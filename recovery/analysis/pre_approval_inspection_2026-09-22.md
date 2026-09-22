# Pre-Approval Inspection Report — QEVION (2026-09-22)

**Status:** APPROVED by operator on 2026-09-22 (all decisions D1–D15, all recommendations, 36 approval points).
**Purpose of this copy:** preserve the analysis the approved architecture rests on, so no executor depends on chat history.
Repository at inspection: HEAD `a2e15cb`, `main`, 10 commits, documents only (zero code/tests/config/CI/ADRs/evidence).

## 1. Inputs inspected
- `README.md` — "Egyptian Arabic restaurant voice agent", specification phase.
- `docs/QEVION_VOICE_RUNTIME_POC_SPEC_v2.md` v2.3 (1961 lines) — strong provider-neutral voice POC spec; **restaurant-shaped core**
  (order draft = only truth; ORDERING→CONFIRMING task machine; menu tools; restaurant policies).
- `important_rebuild.md` (5273 lines) — operator master prompt: X² general-platform rewrite directives (§0–112) + X³ Configuration
  Copilot directives (§1–50). Not a specification.
- External (verified at source): TypeSafe docs; gist of Egyptian TTS options; OpenAI Realtime; Gemini Live; Pipecat; Smart Turn v3;
  Silero VAD; Habibi-TTS; VoiceTuT-TTS; QwenCleo-ASR; edge-tts.
- Sandbox: Python 3.13, Node 22, ffmpeg, 2 vCPU, ~1 GB RAM, no GPU.
Evidence classification: everything in repo = SPEC-DEFINED; nothing PROVEN; no historical implementation to blame.

## 2. Conflicts and approved resolutions
| # | Conflict | Resolution |
|---|---|---|
| C1 | Restaurant-shaped Core vs generic platform | Core re-founded on Activity / Field / Policy / Outcome; restaurant = Blueprint + tenant data |
| C2 | Monolithic s2s provider contract vs composable ASR/LLM/TTS/VAD | Separate provider role ports + composition layer |
| C3 | Copilot deferred (SP-03/09) vs Copilot as product core | Copilot in scope; billing/RBAC/campaign execution/CRM stay deferred |
| C4 | Inbound-only vs outbound first-class | Direction semantic + opening policy + contact-policy hooks + simulated dial; campaign = design-only |
| C5 | "Refuse to start without credential" vs UI test key | Runtime starts with zero credentials (mock); *real sessions* resolve credentials via CredentialResolver (env → admin store → in-memory ephemeral UI key) |
| C6 | Pipecat default foundation vs no framework dogmatism | Thin WS/AudioWorklet PCM16 transport + direct adapters; Pipecat/LiveKit = future transport-adapter candidates (ADR-0001) |
| C7 | Restaurant task machine vs Activity ≠ dialogue graph | Generic data-driven activity machine + field-completion; constrained flow = optional mode |
| C8 | `service_id` vs Line/Activity | `tenant_id / line_id / activity_id / activity_version` |
| C9 | Operator-only console vs Configuration Center + Admin | One web app, three modes |
| C10 | Dialect parsers in tools vs no `if Egyptian` | `locale_pack.v1` data + pure library |
| C11 | TypeSafe meaning | Typed-decision provider; OPTIONAL adapter behind `decision.v1`; deterministic-first |
| C12 | Authoritative document | New `QEVION_PLATFORM_SPEC_v3.md`; v2.3 archived with change map; master prompt → `docs/inputs/` |

## 3. External reference verdicts
- TypeSafe: useful for confirmation fallback, turn-signal fan-out, claim post-check, graders, copilot classification — only behind `decision.v1`. Never reasoning/truth/state. Commercial API → optional.
- Habibi-TTS: code MIT; EGY specialized model Apache-2.0; Unified/SAU/UAE CC-BY-NC-SA (non-commercial). GPU. VERIFIED CANDIDATE (EGY only).
- VoiceTuT-TTS: Apache-2.0; base OmniVoice license UNVERIFIED; T4 TTFA 1.68 s (not realtime on T4). CANDIDATE.
- QwenCleo-ASR: Apache-2.0 (Qwen3-ASR terms); WER 19.85% Egyptian+code-switch; streaming via vLLM nightly on Ampere+. CANDIDATE.
- edge-tts: unofficial Microsoft endpoint; commercial use without Azure violates MS ToS → REJECTED for product; Azure Speech `ar-EG` is the licensed path.
- Coqui XTTS-v2: CPML non-commercial → REJECTED.
- OpenAI Realtime: GA; `turn_detection: null` + manual commit; semantic_vad; ephemeral tokens; WebRTC/WS/SIP → first s2s provider.
- Gemini Live: native audio, function calling, session resumption → second provider (stub + fixtures).
- Smart Turn v3.x: open semantic end-of-turn, 23 languages incl. Arabic, CPU ~12 ms → turn-port candidate; Egyptian quality UNVERIFIED.
- Silero VAD: MIT, CPU → default VAD.

## 4. Gap analysis (approved handling)
REQUIRED: generic core; provider role ports; plane separation; Copilot; outbound direction; Outcome Engine; Line primitive; minimal Admin;
generic activity machine; FieldStore with provenance; Claim Governor; uncertainty policy; entity focus/reference resolution; multi-intent/topic/
correction handling; Blueprint schema + validator; Preflight; readiness lifecycle; dynamic discovery + prioritization; capability registry;
decision provenance; copilot failure isolation; ingestion pipeline with provenance/source priority/conflicts; knowledge versioning; real voice
path; turn taxonomy; 7-step interruption with timestamps; cascade composition (contract + mocks); echo discipline; locale packs; language
capability registry; pronunciation layer; Egyptian quality measurement; provider role separation; credential resolver; generic platform tools;
tool adapter contract (in-memory); handoff sinks (console); copilot security; cross-tenant tests both planes; PDPL posture incl. uploads;
consent/opt-out hooks; copilot observability; simulation + adversarial; copilot evaluation; replay boundary; recovery system; license gate;
reference registry.
RECOMMENDED: repetition root-cause detector; Arabizi normalizer; scalability seams.
DEFERRED (seam only): router; campaign; semantic retrieval; http tool adapters; webhook sinks; hosted deploy; telephony; GPU local adapters.

## 5. Approved phase plan
P0 Foundation → P1 Generic Core → P2 Knowledge + Blueprint + Preflight → P3 Copilot + Web → P4 Voice Runtime →
P5 Simulation + Activation + Outbound → P6 Evaluation + Evidence + Preview. Each: Plan → Implement → Self Review → Test → Fix →
Re-test → Security → Evidence → Checkpoint → Commit → Continue.
