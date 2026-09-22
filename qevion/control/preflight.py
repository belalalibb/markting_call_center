"""Preflight (§11 QV-PRE-001..004): deterministic Control-Plane check that returns `qevion.preflight.v1`.

READY means every check passed or only WARN findings remain. BLOCKED lists every finding with a reason code,
JSON path, message and fix hint. Capability facts come from the Capability Registry (QV-PRE-003 / QV-CAP-002),
never from hardcoded assumptions: what the registry does not assert is UNVERIFIED and blocks real activation.

Inputs are contracts only. No business vocabulary: the checks read the Blueprint's own declared names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.common import Channel, Direction
from qevion.contracts.composition import CapabilityRegistry, CapabilityState, Composition, CompositionMode
from qevion.contracts.control import PreflightFinding, PreflightReason, PreflightResult
from qevion.contracts.provider import ProviderRole
from qevion.contracts.tenant import LocalePack, Tenant, VoiceProfile
from qevion.contracts.tool import ToolDeclaration

R = PreflightReason

# Voice channels need an audio-capable composition; text-only Activities do not.
_VOICE_CHANNELS = (
    {Channel.BROWSER_VOICE, Channel.TELEPHONY} if hasattr(Channel, "TELEPHONY") else {Channel.BROWSER_VOICE}
)

# Rule grammar accepted by the deterministic decision adapter (mirrors adapters/decision/rules.py; Preflight only
# checks *references*, never evaluates business truth).
_RULE_ATOM = re.compile(
    r"^\s*(?:(\w+)\s+recorded|(\w+)\.\.(\w+)\s+recorded|(\w+)\s+accepted|(\w+)\s*(==|!=|>=|<=|>|<)\s*.+?|([a-z_]+))\s*$"
)


@dataclass
class PreflightContext:
    """Everything Preflight may consult besides the Blueprint. All optional; absence → UNVERIFIED findings."""

    registry: CapabilityRegistry | None = None
    composition: Composition | None = None
    tenant: Tenant | None = None
    tool_declarations: dict[str, ToolDeclaration] = field(default_factory=dict)
    tenant_allowed_tools: set[str] | None = None  # None = tenant has not restricted tools
    locale_packs: dict[str, LocalePack] = field(default_factory=dict)
    voice_profiles: dict[str, VoiceProfile] = field(default_factory=dict)
    knowledge_conflicts: list[str] = field(default_factory=list)  # unresolved DATA_CONFLICT ids from knowledge plane
    blocked_licenses: set[str] = field(default_factory=set)  # adapter names rejected by the license registry
    strict_capabilities: bool = True  # UNVERIFIED provider capability blocks (real activation) vs warns (simulation)


@dataclass
class Preflight:
    """Run every check; collect findings; decide READY/BLOCKED."""

    ctx: PreflightContext = field(default_factory=PreflightContext)

    def run(self, bp: ActivityBlueprint) -> PreflightResult:
        f: list[PreflightFinding] = []
        for check in (
            self._fields,
            self._outcome_schema,
            self._completion,
            self._tools,
            self._policies,
            self._escalation,
            self._knowledge,
            self._decisions,
            self._coverage,
            self._outbound,
            self._channels_and_composition,
            self._locale_and_voice,
            self._licenses,
        ):
            f.extend(check(bp))
        status = "BLOCKED" if any(x.severity == "BLOCK" for x in f) else "READY"
        return PreflightResult(
            activity_id=bp.identity.activity_id,
            activity_version=bp.identity.version,
            composition_id=self.ctx.composition.composition_id if self.ctx.composition else None,
            status=status,
            findings=f,
        )

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _block(reason: R, path: str, msg: str, hint: str | None = None) -> PreflightFinding:
        return PreflightFinding(reason=reason, path=path, message=msg, severity="BLOCK", fix_hint=hint)

    @staticmethod
    def _warn(reason: R, path: str, msg: str, hint: str | None = None) -> PreflightFinding:
        return PreflightFinding(reason=reason, path=path, message=msg, severity="WARN", fix_hint=hint)

    # ------------------------------------------------------------------ checks
    def _fields(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        out: list[PreflightFinding] = []
        seen: set[str] = set()
        for section in ("required", "optional"):
            for i, spec in enumerate(getattr(bp.data, section)):
                p = f"data.{section}[{i}]"
                if spec.name in seen:
                    out.append(self._block(R.INCOMPLETE_FIELD_DEFINITION, p, f"duplicate field '{spec.name}'"))
                seen.add(spec.name)
                if spec.type == "enum" and not spec.enum_values:
                    out.append(
                        self._block(R.INCOMPLETE_FIELD_DEFINITION, p, f"enum field '{spec.name}' has no enum_values")
                    )
                if not spec.clarification_hint:
                    out.append(
                        self._warn(
                            R.INCOMPLETE_FIELD_DEFINITION,
                            p,
                            f"field '{spec.name}' has no clarification_hint",
                            "Add the question the agent should ask when this datum is missing or unclear.",
                        )
                    )
        if bp.constrained_flow and bp.constrained_flow.enabled:
            for j, step in enumerate(bp.constrained_flow.steps):
                if step not in seen:
                    out.append(
                        self._block(R.INVALID_CONFIG, f"constrained_flow.steps[{j}]", f"step '{step}' is not a field")
                    )
        return out

    def _outcome_schema(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        out: list[PreflightFinding] = []
        names = {s.name for s in [*bp.data.required, *bp.data.optional]}
        if not bp.outcome_schema.primary:
            out.append(self._block(R.MISSING_OUTCOME_SCHEMA, "outcome_schema.primary", "no primary outcomes"))
        for i, of in enumerate(bp.outcome_schema.fields):
            src = of.source_field or of.name
            if "." in src:  # tool-derived, e.g. submit_record.record_id
                tool = src.split(".", 1)[0]
                if tool not in bp.tools.permissions:
                    out.append(
                        self._block(
                            R.MISSING_OUTCOME_SCHEMA,
                            f"outcome_schema.fields[{i}]",
                            f"outcome field '{of.name}' sources tool '{tool}' which the Activity does not declare",
                        )
                    )
            elif src not in names:
                out.append(
                    self._block(
                        R.MISSING_OUTCOME_SCHEMA,
                        f"outcome_schema.fields[{i}]",
                        f"outcome field '{of.name}' sources unknown data field '{src}'",
                        "Declare the field under data.required/optional or set source_field.",
                    )
                )
        return out

    def _completion(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        out: list[PreflightFinding] = []
        c = bp.completion
        if not c.success_rules and not c.exit_rules:
            out.append(
                self._block(
                    R.IMPOSSIBLE_COMPLETION_CRITERIA,
                    "completion",
                    "no success_rules and no exit_rules — the Activity can never complete",
                )
            )
        names = {s.name for s in [*bp.data.required, *bp.data.optional]}
        tools = set(bp.tools.permissions)
        primary = set(bp.outcome_schema.primary)
        for kind in ("success_rules", "failure_rules", "exit_rules"):
            for i, raw in enumerate(getattr(c, kind)):
                p = f"completion.{kind}[{i}]"
                expr, _, target = raw.partition("=>")
                if target and target.strip() not in primary:
                    out.append(
                        self._block(
                            R.IMPOSSIBLE_COMPLETION_CRITERIA,
                            p,
                            f"exit target '{target.strip()}' not in outcome_schema.primary",
                        )
                    )
                for atom in expr.split(" AND "):
                    m = _RULE_ATOM.match(atom)
                    if not m:
                        out.append(
                            self._block(
                                R.IMPOSSIBLE_COMPLETION_CRITERIA, p, f"rule atom '{atom.strip()}' is not evaluable"
                            )
                        )
                        continue
                    rec, lo, hi, acc, cmp_, _op, flag = m.groups()
                    if rec and rec not in names:
                        out.append(self._block(R.IMPOSSIBLE_COMPLETION_CRITERIA, p, f"'{rec}' is not a field"))
                    if lo and not any(n.startswith(re.sub(r"\d+$", "", lo)) for n in names):
                        out.append(
                            self._block(R.IMPOSSIBLE_COMPLETION_CRITERIA, p, f"range '{lo}..{hi}' matches no field")
                        )
                    if acc and acc not in tools:
                        out.append(
                            self._block(R.IMPOSSIBLE_COMPLETION_CRITERIA, p, f"'{acc} accepted' but tool not declared")
                        )
                    if cmp_ and cmp_ not in names:
                        out.append(self._block(R.IMPOSSIBLE_COMPLETION_CRITERIA, p, f"'{cmp_}' is not a field"))
                    _ = flag  # bare flags are session facts (opt_out, wrong_person, <tool>_completed) — accepted
        if c.success_rules and c.failure_rules and set(c.success_rules) & set(c.failure_rules):
            out.append(self._block(R.CONTRADICTORY_POLICIES, "completion", "a rule is both success and failure"))
        return out

    def _tools(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        out: list[PreflightFinding] = []
        decls = self.ctx.tool_declarations
        allowed = self.ctx.tenant_allowed_tools
        for i, ref in enumerate(bp.tools.required):
            p = f"tools.required[{i}]"
            if decls and ref.tool_id not in decls:
                out.append(
                    self._block(
                        R.MISSING_REQUIRED_TOOL,
                        p,
                        f"required tool '{ref.tool_id}' has no registered declaration/backend",
                        "Register the tool (platform catalog or business tool) or remove it from tools.required.",
                    )
                )
            if allowed is not None and ref.tool_id not in allowed:
                out.append(
                    self._block(
                        R.TOOL_NOT_AUTHORIZED_FOR_TENANT, p, f"tool '{ref.tool_id}' not authorized for this tenant"
                    )
                )
        for i, ref in enumerate(bp.tools.optional):
            if allowed is not None and ref.tool_id not in allowed:
                out.append(
                    self._warn(
                        R.TOOL_NOT_AUTHORIZED_FOR_TENANT,
                        f"tools.optional[{i}]",
                        f"optional tool '{ref.tool_id}' not authorized for this tenant; it will be unavailable",
                    )
                )
        for tid, perm in bp.tools.permissions.items():
            p = f"tools.permissions.{tid}"
            decl = decls.get(tid)
            if decl and decl.impact.value != perm.impact:
                out.append(
                    self._block(
                        R.INVALID_CONFIG,
                        p,
                        f"impact '{perm.impact}' contradicts declaration '{decl.impact.value}'",
                        "The pipeline rejects impact mismatches at step 4; align the permission.",
                    )
                )
            waived = any(d.item_path == f"{p}.confirmation" and d.approved_by for d in bp.version_metadata.decisions)
            if (
                perm.impact == "write"
                and perm.confirmation == "none"
                and decl
                and decl.confirmation != "none"
                and not waived
            ):
                out.append(
                    self._block(
                        R.INCOMPATIBLE_CONFIRMATION_RULE,
                        p,
                        f"'{tid}' is declared confirm_before_execute but the Activity sets confirmation: none",
                        "Keep confirm_before_execute or record an approved Decision waiving it.",
                    )
                )
            if perm.confirmation == "confirm_before_execute" and perm.impact == "read":
                out.append(
                    self._warn(
                        R.INCOMPATIBLE_CONFIRMATION_RULE, p, f"read tool '{tid}' requires confirmation — unusual"
                    )
                )
        # write tools with provenance_required TOOL_VERIFIED fields need a verify path
        needs_verify = [s.name for s in bp.data.required if s.provenance_required.value == "TOOL_VERIFIED"]
        if needs_verify and "verify_field" not in bp.tools.permissions:
            out.append(
                self._block(
                    R.MISSING_REQUIRED_TOOL,
                    "tools.required",
                    f"fields {needs_verify} require TOOL_VERIFIED provenance but 'verify_field' is not declared",
                    "Add verify_field (or a business verification tool) so these fields can ever satisfy readiness.",
                )
            )
        return out

    def _policies(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        out: list[PreflightFinding] = []
        pol = bp.policies
        allowed = {c.claim_type for c in pol.allowed_claims}
        prohibited = {c.claim_type for c in pol.prohibited_claims}
        for ct in sorted(allowed & prohibited):
            out.append(
                self._block(
                    R.CONTRADICTORY_POLICIES,
                    "policies.allowed_claims",
                    f"claim type '{ct}' is both allowed and prohibited",
                )
            )
        if pol.unknown_question_policy is None or pol.unknown_question_policy.default is None:
            out.append(
                self._block(R.UNDEFINED_UNKNOWN_QUESTION_POLICY, "policies.unknown_question_policy", "no default")
            )
        for i, ov in enumerate(pol.unknown_question_policy.overrides):
            if not ov.topic_pattern.strip():
                out.append(
                    self._block(
                        R.INVALID_CONFIG, f"policies.unknown_question_policy.overrides[{i}]", "empty topic_pattern"
                    )
                )
        handoff_behaviors = {"OFFER_HUMAN_HANDOFF"}
        uses_handoff = pol.unknown_question_policy.default.value in handoff_behaviors or any(
            o.behavior.value in handoff_behaviors for o in pol.unknown_question_policy.overrides
        )
        if uses_handoff and "request_handoff" not in bp.tools.permissions and not bp.handoff_rules:
            out.append(
                self._block(
                    R.UNDEFINED_ESCALATION,
                    "policies.unknown_question_policy",
                    "OFFER_HUMAN_HANDOFF configured but no request_handoff tool and no handoff_rules",
                    "Declare request_handoff and at least one handoff_rules entry with a destination_ref.",
                )
            )
        if bp.objective.optimization_bounds.respect_opt_out and pol.opt_out is None:
            out.append(
                self._warn(
                    R.INVALID_CONFIG,
                    "policies.opt_out",
                    "respect_opt_out is set but no opt_out policy (phrases_ref/action) is configured",
                )
            )
        return out

    def _escalation(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        out: list[PreflightFinding] = []
        names = {s.name for s in [*bp.data.required, *bp.data.optional]}
        for i, rule in enumerate(bp.policies.escalation):
            p = f"policies.escalation[{i}]"
            if rule.action == "request_handoff" and not bp.handoff_rules:
                out.append(
                    self._block(
                        R.UNDEFINED_ESCALATION, p, f"escalation '{rule.trigger}' hands off but no handoff_rules"
                    )
                )
        for i, hr in enumerate(bp.handoff_rules):
            p = f"handoff_rules[{i}]"
            if not hr.destination_ref.strip():
                out.append(self._block(R.UNDEFINED_ESCALATION, p, "empty destination_ref"))
            for fld in hr.context_projection:
                if fld not in names:
                    out.append(
                        self._block(R.UNDEFINED_ESCALATION, p, f"context_projection field '{fld}' is not a field")
                    )
        return out

    def _knowledge(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        out: list[PreflightFinding] = []
        for i, req in enumerate(bp.knowledge.requirements):
            p = f"knowledge.requirements[{i}]"
            if req.status == "MISSING":
                out.append(
                    self._block(
                        R.MISSING_REQUIRED_KNOWLEDGE,
                        p,
                        f"knowledge domain '{req.domain}' is MISSING",
                        "Upload/approve a source that satisfies this requirement or remove it.",
                    )
                )
            elif req.status == "PARTIAL":
                out.append(self._warn(R.MISSING_REQUIRED_KNOWLEDGE, p, f"knowledge domain '{req.domain}' is PARTIAL"))
        needs_kb = [s.name for s in bp.data.required if s.provenance_required.value == "KNOWLEDGE_APPROVED"]
        if needs_kb and not bp.knowledge.sources:
            out.append(
                self._block(
                    R.MISSING_REQUIRED_KNOWLEDGE,
                    "knowledge.sources",
                    f"fields {needs_kb} require KNOWLEDGE_APPROVED provenance but no knowledge sources are bound",
                )
            )
        for cid in self.ctx.knowledge_conflicts:
            out.append(
                self._block(
                    R.UNRESOLVED_KNOWLEDGE_CONFLICT,
                    "knowledge",
                    f"unresolved knowledge conflict {cid}",
                    "Resolve in the Config Center (pick the authoritative source) before activation.",
                )
            )
        for src_id, ver in bp.version_metadata.pinned.knowledge_versions.items():
            if not any(s.source_id == src_id for s in bp.knowledge.sources):
                out.append(
                    self._warn(
                        R.INVALID_CONFIG,
                        "version_metadata.pinned.knowledge_versions",
                        f"pinned '{src_id}@{ver}' not in knowledge.sources",
                    )
                )
        return out

    def _decisions(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        out: list[PreflightFinding] = []
        for i, d in enumerate(bp.version_metadata.decisions):
            if d.approved_by is None:
                out.append(
                    self._block(
                        R.UNAPPROVED_BUSINESS_DECISION,
                        f"version_metadata.decisions[{i}]",
                        f"'{d.item_path}' proposed by {d.proposed_by.value} has no operator approval",
                        "Approve or reject it in the Config Center review step.",
                    )
                )
        return out

    def _coverage(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        """QV-COV-004: ASK_OWNER items block only when they gate execution or carry policy risk; else warn."""
        out: list[PreflightFinding] = []
        for i, q in enumerate(bp.coverage.questions):
            p = f"coverage.questions[{i}]"
            if q.status == "ASK_OWNER":
                blocking = q.handling in ("TOOL", "HANDOFF")
                mk = self._block if blocking else self._warn
                out.append(mk(R.UNAPPROVED_BUSINESS_DECISION, p, f"question '{q.id}' still ASK_OWNER"))
            if q.handling == "TOOL" and q.answer_ref and q.answer_ref not in bp.tools.permissions:
                out.append(self._block(R.MISSING_REQUIRED_TOOL, p, f"question '{q.id}' routes to undeclared tool"))
            if q.handling == "HANDOFF" and not bp.handoff_rules and "request_handoff" not in bp.tools.permissions:
                out.append(self._block(R.UNDEFINED_ESCALATION, p, f"question '{q.id}' hands off but no handoff path"))
        for i, ob in enumerate(bp.coverage.objections):
            if ob.status == "ASK_OWNER":
                out.append(
                    self._warn(
                        R.UNAPPROVED_BUSINESS_DECISION,
                        f"coverage.objections[{i}]",
                        f"objection '{ob.id}' has no approved response",
                    )
                )
        return out

    def _outbound(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        out: list[PreflightFinding] = []
        if bp.direction != Direction.OUTBOUND:
            return out
        hooks = bp.policies.contact_policy_hooks
        if hooks is None:
            out.append(self._block(R.CONTACT_POLICY_MISSING_FOR_OUTBOUND, "policies.contact_policy_hooks", "missing"))
            return out
        if hooks.consent_required and not any(d.when.upper() == "OPENING" for d in bp.policies.disclosures):
            out.append(
                self._block(
                    R.CONTACT_POLICY_MISSING_FOR_OUTBOUND,
                    "policies.disclosures",
                    "consent_required but no OPENING disclosure",
                    "Add a disclosure with when: OPENING (identity + purpose + consent).",
                )
            )
        if not hooks.contact_window:
            out.append(
                self._warn(R.CONTACT_POLICY_MISSING_FOR_OUTBOUND, "policies.contact_policy_hooks", "no contact_window")
            )
        return out

    def _channels_and_composition(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        out: list[PreflightFinding] = []
        comp, reg = self.ctx.composition, self.ctx.registry
        if self.ctx.tenant is not None and comp is not None:
            for b in comp.bindings:
                if b.adapter not in self.ctx.tenant.enabled_providers and b.role in (
                    ProviderRole.S2S,
                    ProviderRole.LLM,
                    ProviderRole.ASR,
                    ProviderRole.TTS,
                ):
                    out.append(
                        self._block(
                            R.PROVIDER_CAPABILITY_UNAVAILABLE,
                            f"composition.bindings[{b.role.value}]",
                            f"provider '{b.adapter}' not enabled for tenant",
                        )
                    )
        voice = any(ch in _VOICE_CHANNELS for ch in bp.channels)
        if comp is None:
            out.append(
                self._block(
                    R.INVALID_CONFIG,
                    "version_metadata.pinned.composition_config",
                    "no composition pinned/resolved",
                    "Pin a composition config (e.g. comp_mock_s2s_v1) so Preflight can verify capabilities.",
                )
            )
            return out
        if reg is None:
            out.append(
                self._block(
                    R.UNSUPPORTED_CAPABILITY,
                    "capability_registry",
                    "no Capability Registry supplied — nothing is verifiable",
                )
            )
            return out
        lang_cap = f"language:{bp.locale.locale}"
        wanted: list[tuple[ProviderRole, str, R]] = []
        if comp.mode is CompositionMode.S2S:
            wanted += [(ProviderRole.S2S, lang_cap, R.UNSUPPORTED_LOCALE_COMBINATION)]
            if bp.tools.required or bp.tools.optional:
                wanted.append((ProviderRole.S2S, "feature:tool_calls", R.UNSUPPORTED_CAPABILITY))
            if voice:
                wanted += [
                    (ProviderRole.S2S, "audio:pcm16_24k", R.UNSUPPORTED_CAPABILITY),
                    (ProviderRole.S2S, "feature:barge_in", R.UNSUPPORTED_CAPABILITY),
                ]
        else:
            wanted += [
                (ProviderRole.ASR, lang_cap, R.UNSUPPORTED_LOCALE_COMBINATION),
                (ProviderRole.TTS, lang_cap, R.UNSUPPORTED_LOCALE_COMBINATION),
            ]
            if bp.tools.required or bp.tools.optional:
                wanted.append((ProviderRole.LLM, "feature:tool_calls", R.UNSUPPORTED_CAPABILITY))
        if voice:
            wanted.append((ProviderRole.TURN, "feature:barge_in", R.UNSUPPORTED_CAPABILITY))
        for role, cap, reason in wanted:
            bound = next((x for x in comp.bindings if x.role == role), None)
            if bound is None:
                out.append(self._block(R.INVALID_CONFIG, "composition.bindings", f"no binding for role {role.value}"))
                continue
            b = bound
            ac = reg.find(role, b.adapter)
            state = ac.state_of(cap) if ac else CapabilityState.UNVERIFIED
            if cap.startswith("language:") and ac and state is CapabilityState.UNVERIFIED:
                state = ac.state_of("language:any")  # language-agnostic components (energy VAD) declare `any`
            p = f"composition.bindings[{role.value}]={b.adapter}"
            if state is CapabilityState.UNSUPPORTED:
                out.append(self._block(reason, p, f"{cap} is UNSUPPORTED"))
            elif state is CapabilityState.UNVERIFIED:
                mk = self._block if self.ctx.strict_capabilities else self._warn
                out.append(
                    mk(
                        R.PROVIDER_CAPABILITY_UNAVAILABLE,
                        p,
                        f"{cap} is UNVERIFIED for '{b.adapter}' (QV-CAP-004: locale code is not proof)",
                        "Run the capability negotiation/evidence test for this adapter, or choose a verified one.",
                    )
                )
            elif state is CapabilityState.PARTIAL:
                out.append(self._warn(reason, p, f"{cap} is PARTIAL for '{b.adapter}'"))
        for ch in bp.channels:
            if ch not in Channel.__members__.values():
                out.append(self._block(R.UNSUPPORTED_CHANNEL, "channels", f"unknown channel {ch}"))
        return out

    def _locale_and_voice(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        out: list[PreflightFinding] = []
        lp_ref = bp.locale.locale_pack_ref or bp.version_metadata.pinned.locale_pack
        if lp_ref:
            lp = self.ctx.locale_packs.get(lp_ref)
            if lp is None:
                out.append(
                    self._block(
                        R.UNSUPPORTED_LOCALE_COMBINATION, "locale.locale_pack_ref", f"locale pack '{lp_ref}' not found"
                    )
                )
            elif lp.locale != bp.locale.locale:
                out.append(
                    self._block(
                        R.UNSUPPORTED_LOCALE_COMBINATION,
                        "locale.locale_pack_ref",
                        f"locale pack is {lp.locale}, Activity is {bp.locale.locale}",
                    )
                )
        elif self.ctx.locale_packs:
            out.append(self._warn(R.UNSUPPORTED_LOCALE_COMBINATION, "locale.locale_pack_ref", "no locale pack bound"))
        voice = any(ch in _VOICE_CHANNELS for ch in bp.channels)
        vp_ref = bp.locale.voice_profile_ref or bp.version_metadata.pinned.voice_profile
        if voice:
            if not vp_ref:
                out.append(
                    self._block(
                        R.VOICE_UNAVAILABLE, "locale.voice_profile_ref", "voice channel without a voice profile"
                    )
                )
            else:
                vp = self.ctx.voice_profiles.get(vp_ref)
                if vp is None:
                    out.append(
                        self._block(
                            R.VOICE_UNAVAILABLE, "locale.voice_profile_ref", f"voice profile '{vp_ref}' not found"
                        )
                    )
                elif self.ctx.composition is not None:
                    speaking = (
                        ProviderRole.S2S if self.ctx.composition.mode is CompositionMode.S2S else ProviderRole.TTS
                    )
                    adapter = self.ctx.composition.binding(speaking).adapter
                    if adapter not in vp.provider_voice_map:
                        out.append(
                            self._block(
                                R.VOICE_UNAVAILABLE,
                                "locale.voice_profile_ref",
                                f"voice profile '{vp_ref}' has no voice for adapter '{adapter}'",
                                "Add a provider_voice_map entry for this adapter.",
                            )
                        )
        return out

    def _licenses(self, bp: ActivityBlueprint) -> list[PreflightFinding]:
        out: list[PreflightFinding] = []
        if self.ctx.composition is None:
            return out
        for b in self.ctx.composition.bindings:
            if b.adapter in self.ctx.blocked_licenses:
                out.append(
                    self._block(
                        R.LICENSE_BLOCKED_COMPONENT,
                        f"composition.bindings[{b.role.value}]",
                        f"adapter '{b.adapter}' is license-blocked for product use (docs/registry/licenses.yaml)",
                    )
                )
        return out


def run_preflight(bp: ActivityBlueprint, ctx: PreflightContext | None = None) -> PreflightResult:
    return Preflight(ctx or PreflightContext()).run(bp)


__all__ = ["Preflight", "PreflightContext", "run_preflight"]
