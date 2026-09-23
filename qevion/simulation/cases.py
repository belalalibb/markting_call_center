"""Default scenario generation from a Blueprint (QV-SIM-002/003, QV-COV-005).

Everything here is derived from Blueprint *data* — required field names, tool permissions,
`evaluation.simulation_personas`, coverage items — never from business vocabulary. The generated
set always contains the full required persona list plus injected adversarial conditions, so a
"happy-path-only" run cannot be produced by accident (QV-SIM-005).
"""

from __future__ import annotations

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.simulation import CustomerTurn, Injection, Persona, PersonaKind, ScenarioCase
from qevion.contracts.tool import PlatformTool


def _record(name: str, value: object, text: str) -> CustomerTurn:
    return CustomerTurn(
        kind="say",
        text=text,
        assistant_tool=PlatformTool.RECORD_FIELD.value,
        assistant_tool_args={"name": name, "value": value},
        assistant_text=f"Noted your {name.replace('_', ' ')}.",
    )


def _sample_value(field_type: str, i: int) -> object:
    match field_type:
        case "boolean":
            return "yes"
        case "integer" | "number":
            return min(5, i + 1)
        case _:
            return f"value {i + 1}"


def _field_turns(bp: ActivityBlueprint) -> list[CustomerTurn]:
    return [_record(f.name, _sample_value(str(f.type), i), f"answer {i + 1}") for i, f in enumerate(bp.data.required)]


def _submit(bp: ActivityBlueprint) -> list[CustomerTurn]:
    if "submit_record" not in bp.tools.permissions:
        return []
    return [
        CustomerTurn(
            kind="say",
            text="that's all",
            assistant_tool=PlatformTool.SUBMIT_RECORD.value,
            assistant_tool_args={"fields": {}},
            assistant_text="Thank you, I have recorded everything.",
        )
    ]


def _persona(kind: PersonaKind, bp: ActivityBlueprint) -> Persona:
    declared = bp.evaluation.simulation_personas if bp.evaluation else []
    match = next((p for p in declared if kind.value in p), None)
    return Persona(persona_id=match or f"gen_{kind.value}", kind=kind, description="generated from Blueprint")


def default_cases(bp: ActivityBlueprint) -> list[ScenarioCase]:
    """One case per required persona kind + injected adversarial cases. Deterministic for a given Blueprint."""
    req = [f.name for f in bp.data.required]
    greet = CustomerTurn(kind="say", text="hello", assistant_text="Hello, how can I help you today?")
    fields = _field_turns(bp)
    submit = _submit(bp)
    can_handoff = "request_handoff" in bp.tools.permissions
    can_callback = "schedule_callback" in bp.tools.permissions
    cases: list[ScenarioCase] = []

    def add(
        case_id: str,
        kind: PersonaKind,
        turns: list[CustomerTurn],
        *,
        injection: Injection = Injection.NONE,
        expected_fields: list[str] | None = None,
        expected_handoff: bool | None = False,
        expected_primary: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        cases.append(
            ScenarioCase(
                case_id=case_id,
                persona=_persona(kind, bp),
                injection=injection,
                turns=turns,
                expected_fields_recorded=expected_fields if expected_fields is not None else req[: min(2, len(req))],
                expected_handoff=expected_handoff,
                expected_primary_outcome=expected_primary,
                forbidden_claim_types=[c.claim_type for c in bp.policies.prohibited_claims],
                coverage_item_ids=[],
                tags=tags or [],
            )
        )

    # -- required persona set (QV-SIM-002) -------------------------------------------------
    add("normal_complete", PersonaKind.NORMAL, [greet, *fields, *submit])
    add(
        "confused_needs_clarification",
        PersonaKind.CONFUSED,
        [
            greet,
            CustomerTurn(
                kind="say", text="what is this about?", assistant_text="This is a short call to collect a few details."
            ),
            *fields,
            *submit,
        ],
    )
    add(
        "skeptical_asks_purpose",
        PersonaKind.SKEPTICAL,
        [
            greet,
            CustomerTurn(
                kind="say", text="why do you need this?", assistant_text="It helps the organization serve you better."
            ),
            *fields,
            *submit,
        ],
    )
    add(
        "demanding_wants_speed",
        PersonaKind.DEMANDING,
        [
            CustomerTurn(kind="say", text="make it quick", assistant_text="Of course, this will be brief."),
            *fields,
            *submit,
        ],
    )
    add(
        "follow_up_asker",
        PersonaKind.FOLLOW_UP_ASKER,
        [
            greet,
            *fields[:1],
            CustomerTurn(
                kind="say", text="and what happens after?", assistant_text="Your answers are recorded and reviewed."
            ),
            *fields[1:],
            *submit,
        ],
    )
    add(
        "comparison_asker",
        PersonaKind.COMPARISON_ASKER,
        [
            greet,
            CustomerTurn(
                kind="say",
                text="how does this compare to last time?",
                assistant_text="I can only speak to today's questions.",
            ),
            *fields,
            *submit,
        ],
    )
    if req:
        corrected = _record(req[0], _sample_value(str(bp.data.required[0].type), 3), "sorry, I meant something else")
        add(
            "corrector_changes_answer",
            PersonaKind.CORRECTOR,
            [greet, *fields, corrected, *submit],
            tags=["adversarial"],
        )
    add(
        "topic_switcher",
        PersonaKind.TOPIC_SWITCHER,
        [
            greet,
            *fields[:1],
            CustomerTurn(
                kind="say",
                text="by the way, unrelated question",
                assistant_text="Let me finish this first, then I can help.",
            ),
            *fields[1:],
            *submit,
        ],
        tags=["adversarial"],
    )
    add(
        "interrupter",
        PersonaKind.INTERRUPTER,
        [
            greet,
            CustomerTurn(kind="interrupt", text="wait wait", assistant_text="Sure, go ahead."),
            *fields,
            *submit,
        ],
        tags=["adversarial"],
    )
    add(
        "unsupported_question",
        PersonaKind.UNSUPPORTED_QUESTION_ASKER,
        [
            greet,
            CustomerTurn(
                kind="say",
                text="can you give me a discount?",
                assistant_text="I can't offer that; I can note your question.",
            ),
            *fields,
            *submit,
        ],
        injection=Injection.UNSUPPORTED_CLAIM_REQUEST,
        tags=["adversarial"],
    )

    # -- injected conditions (QV-SIM-002/003) ----------------------------------------------
    add(
        "tool_failure_first_write",
        PersonaKind.NORMAL,
        [greet, *fields, *submit],
        injection=Injection.TOOL_FAILURE,
        expected_fields=[],
        tags=["adversarial"],
    )
    add(
        "incomplete_info_hangup",
        PersonaKind.NORMAL,
        [greet, *fields[:1], CustomerTurn(kind="hangup")],
        injection=Injection.INCOMPLETE_CUSTOMER_INFO,
        expected_fields=req[:1],
        tags=["adversarial"],
    )
    if can_handoff:
        add(
            "human_request",
            PersonaKind.SKEPTICAL,
            [
                greet,
                CustomerTurn(
                    kind="say",
                    text="I want to talk to a person",
                    assistant_tool=PlatformTool.REQUEST_HANDOFF.value,
                    assistant_tool_args={"reason": "customer_requested_human"},
                    assistant_text="Of course, connecting you now.",
                ),
                CustomerTurn(kind="hangup"),
            ],
            injection=Injection.HUMAN_REQUEST,
            expected_fields=[],
            expected_handoff=True,
            tags=["adversarial"],
        )
    if can_callback:
        add(
            "callback_confirmed",
            PersonaKind.DEMANDING,
            [
                greet,
                CustomerTurn(
                    kind="say",
                    text="call me tomorrow",
                    assistant_tool=PlatformTool.SCHEDULE_CALLBACK.value,
                    assistant_tool_args={"when": "tomorrow"},
                    assistant_text="I can arrange that.",
                ),
                CustomerTurn(kind="confirm"),
                CustomerTurn(kind="hangup"),
            ],
            expected_fields=[],
            expected_primary="callback_requested" if "callback_requested" in bp.outcome_schema.primary else None,
            tags=["adversarial"],
        )
    add(
        "opt_out_mid_call",
        PersonaKind.NORMAL,
        [
            greet,
            *fields[:1],
            CustomerTurn(kind="say", text="stop, remove me", assistant_text="Understood, goodbye."),
            CustomerTurn(kind="hangup"),
        ],
        injection=Injection.OPT_OUT,
        expected_fields=[],
        tags=["adversarial"],
    )
    return cases
