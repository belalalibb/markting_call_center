"""Registry of every versioned contract model → schema id. Single source of truth for
``scripts/gen_schemas.py`` and the round-trip tests (QV-EVT-005, QV-ACC-003)."""

from __future__ import annotations

from qevion.contracts import activity, composition, control, event, knowledge, outcome, policy, provider, telemetry, tenant, tool, transport
from qevion.contracts.common import QevionModel

CONTRACTS: dict[str, type[QevionModel]] = {
    "qevion.event.v1": event.Event,
    "qevion.activity.v1": activity.ActivityBlueprint,
    "qevion.policy.v1": policy.PolicyBlock,
    "qevion.tenant.v1": tenant.Tenant,
    "qevion.line.v1": tenant.Line,
    "qevion.locale_pack.v1": tenant.LocalePack,
    "qevion.voice_profile.v1": tenant.VoiceProfile,
    "qevion.capability_registry.v1": composition.CapabilityRegistry,
    "qevion.composition.v1": composition.Composition,
    "qevion.s2s.v1": provider.S2SSessionConfig,
    "qevion.s2s_event.v1": provider.S2SEvent,
    "qevion.llm.v1": provider.LLMRequest,
    "qevion.llm_response.v1": provider.LLMResponse,
    "qevion.asr.v1": provider.ASRRequest,
    "qevion.asr_result.v1": provider.ASRResult,
    "qevion.tts.v1": provider.TTSRequest,
    "qevion.turn.v1": provider.TurnEvent,
    "qevion.decision.v1": provider.DecisionRequest,
    "qevion.decision_result.v1": provider.DecisionResult,
    "qevion.transport.hello.v1": transport.ClientHello,
    "qevion.transport.client.v1": transport.ClientMessage,
    "qevion.transport.server.v1": transport.ServerMessage,
    "qevion.tool.v1": tool.ToolDeclaration,
    "qevion.tool_invocation.v1": tool.ToolInvocation,
    "qevion.tool_outcome.v1": tool.ToolOutcome,
    "qevion.tool_backend.v1": tool.ToolBackendBinding,
    "qevion.knowledge_source.v1": knowledge.KnowledgeSource,
    "qevion.knowledge_fact.v1": knowledge.Fact,
    "qevion.knowledge_gap.v1": knowledge.KnowledgeGap,
    "qevion.knowledge_contradiction.v1": knowledge.Contradiction,
    "qevion.handoff.v1": outcome.HandoffRequest,
    "qevion.handoff_result.v1": outcome.HandoffResult,
    "qevion.sink.v1": outcome.SinkConfig,
    "qevion.outcome.v1": outcome.Outcome,
    "qevion.interaction_record.v1": outcome.InteractionRecord,
    "qevion.preflight.v1": control.PreflightResult,
    "qevion.credential_scope.v1": control.CredentialScope,
    "qevion.metrics.v1": telemetry.LatencySample,
    "qevion.usage.v1": telemetry.UsageRecord,
    "qevion.simulation_report.v1": telemetry.SimulationReport,
}

# §37.3 "design-only" contracts: reserved ids, no model in POC (integration, campaign, router, customer_context, retrieval).
DESIGN_ONLY: tuple[str, ...] = (
    "qevion.integration.v1",
    "qevion.campaign.v1",
    "qevion.router.v1",
    "qevion.customer_context.v1",
    "qevion.retrieval.v1",
)


def schema_filename(schema_id: str) -> str:
    return schema_id.replace("qevion.", "").replace(".", "_") + ".schema.json"
