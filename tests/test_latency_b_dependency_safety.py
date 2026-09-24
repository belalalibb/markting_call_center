"""Option B hardening — controlled dependency-safety scenario (offline, deterministic, fake provider socket).

Scenario per test: independent calls, a dependent call (needs a prior result), a confirmation-gated call, a
write/escalation (barrier) call, and a delayed/missing result. Proves:
  * independent calls in one response → exactly one continuation, only after response.done + all results;
  * a dependent call is necessarily sequential: it can only be requested by a *later* response, which the adapter
    never creates before the earlier batch's results are all delivered;
  * confirmation-gated / barrier calls are never combined (response falls back to one continuation per result);
  * a missing result never becomes implied success: the guard sends an explicit `result_pending, executed:false`
    output *before* continuing, and the model is never continued with a call that has no output at all.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from qevion.adapters.providers import openai_realtime as orl
from qevion.contracts.provider import S2SSessionConfig, ToolCallResult
from qevion.main import _seed
from qevion.runtime.store import RuntimeStore, _batch_barriers

BARRIERS = ["request_handoff", "submit_record"]


class _Sock:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.inbox: asyncio.Queue[str | None] = asyncio.Queue()

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def recv(self) -> str | None:
        return await self.inbox.get()

    async def close(self) -> None:
        self.inbox.put_nowait(None)


async def _session() -> tuple[Any, _Sock]:
    sock = _Sock()

    async def factory(url: str, headers: dict[str, str]) -> _Sock:
        return sock

    cfg = S2SSessionConfig(
        provider="openai_realtime",
        model="gpt-realtime",
        extra={"parallel_tools": True, "batch_barriers": BARRIERS},
    )
    return await orl.OpenAIRealtimeAdapter(socket_factory=factory).open(cfg, credential="sk-test"), sock


async def _feed(sock: _Sock, *msgs: dict[str, Any]) -> None:
    for m in msgs:
        sock.inbox.put_nowait(json.dumps(m))
    await asyncio.sleep(0.05)


def _created(rid: str) -> dict[str, Any]:
    return {"type": "response.created", "response": {"id": rid}}


def _done(rid: str) -> dict[str, Any]:
    return {"type": "response.done", "response": {"id": rid, "status": "completed"}}


def _call(rid: str, cid: str, name: str) -> dict[str, Any]:
    return {
        "type": "response.function_call_arguments.done",
        "response_id": rid,
        "call_id": cid,
        "name": name,
        "arguments": "{}",
    }


def _ops(sock: _Sock) -> list[str]:
    """Ordered provider-bound operations: 'out:<call_id>' for function outputs, 'create' for continuations."""
    out = []
    for m in sock.sent:
        if m["type"] == "response.create":
            out.append("create")
        elif m["type"] == "conversation.item.create" and m["item"]["type"] == "function_call_output":
            out.append("out:" + m["item"]["call_id"])
    return out


def _outputs(sock: _Sock) -> dict[str, dict[str, Any]]:
    return {
        m["item"]["call_id"]: json.loads(m["item"]["output"])
        for m in sock.sent
        if m["type"] == "conversation.item.create" and m["item"]["type"] == "function_call_output"
    }


def test_barrier_set_is_derived_from_blueprint() -> None:
    s = RuntimeStore()
    _seed(s)
    bp = next(r.blueprint for k, r in s.activities.items() if k.startswith("act_order_intake"))
    got = _batch_barriers(bp, s.tool_declarations)
    assert "record_field" not in got  # independent per-field writes may batch
    for tid, perm in bp.tools.permissions.items():
        if perm.confirmation == "confirm_before_execute":
            assert tid in got
    assert all(t not in got for t in ("lookup_knowledge", "compute_quote", "verify_field"))


@pytest.mark.asyncio
async def test_independent_batch_then_dependent_call_stays_sequential() -> None:
    sess, sock = await _session()
    # r1: two independent writes + one independent lookup in ONE response
    await _feed(
        sock,
        _created("r1"),
        _call("r1", "c1", "record_field"),
        _call("r1", "c2", "record_field"),
        _call("r1", "c3", "lookup_knowledge"),
        _done("r1"),
    )
    await sess.send_tool_result(ToolCallResult(call_id="c1", output={"ok": 1}))
    await sess.send_tool_result(ToolCallResult(call_id="c2", output={"ok": 1}))
    assert "create" not in _ops(sock)  # c3 still outstanding → model is NOT continued
    await sess.send_tool_result(ToolCallResult(call_id="c3", output={"facts": []}))
    assert _ops(sock) == ["out:c1", "out:c2", "out:c3", "create"]  # one continuation, after ALL results
    # r2 (created only by that continuation): compute_quote depends on r1's results → strictly after them
    await _feed(sock, _created("r2"), _call("r2", "c4", "compute_quote"), _done("r2"))
    await sess.send_tool_result(ToolCallResult(call_id="c4", output={"total": 1}))
    ops = _ops(sock)
    assert ops.index("out:c4") > ops.index("create")  # dependent result delivered only after the batch continued
    assert ops.count("create") == 2
    await sess.close()


@pytest.mark.asyncio
async def test_confirmation_gated_call_is_never_batched() -> None:
    sess, sock = await _session()
    await _feed(
        sock, _created("r1"), _call("r1", "c1", "record_field"), _call("r1", "c2", "submit_record"), _done("r1")
    )
    await sess.send_tool_result(ToolCallResult(call_id="c1", output={"ok": 1}))
    # barrier present → default path: continuation per delivered result; c2 (awaiting user confirmation) gets
    # no fabricated output at all
    await asyncio.sleep(0.05)
    assert _ops(sock) == ["out:c1", "create"]
    assert "c2" not in _outputs(sock)
    await sess.close()


@pytest.mark.asyncio
async def test_escalation_barrier_not_combined() -> None:
    sess, sock = await _session()
    await _feed(
        sock, _created("r1"), _call("r1", "c1", "lookup_knowledge"), _call("r1", "c2", "request_handoff"), _done("r1")
    )
    await sess.send_tool_result(ToolCallResult(call_id="c1", output={}))
    await sess.send_tool_result(ToolCallResult(call_id="c2", output={}))
    assert _ops(sock) == ["out:c1", "create", "out:c2", "create"]  # identical to the unbatched default path
    await sess.close()


@pytest.mark.asyncio
async def test_missing_result_is_explicit_pending_never_implied_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orl, "BATCH_STALL_S", 0.1)
    sess, sock = await _session()
    await _feed(
        sock, _created("r1"), _call("r1", "c1", "record_field"), _call("r1", "c2", "lookup_knowledge"), _done("r1")
    )
    await sess.send_tool_result(ToolCallResult(call_id="c1", output={"ok": 1}))  # c2 delayed
    await asyncio.sleep(0.25)
    ops = _ops(sock)
    # the continuation is never sent while a call of the batch has NO output
    assert ops == ["out:c1", "out:c2", "create"]
    pending = _outputs(sock)["c2"]
    assert pending["status"] == "result_pending" and pending["executed"] is False
    assert "Do not state or imply it succeeded" in pending["note"]
    # the real (late) result is still delivered, with its own continuation
    await sess.send_tool_result(ToolCallResult(call_id="c2", output={"facts": ["x"]}))
    assert _ops(sock)[-2:] == ["out:c2", "create"]
    await sess.close()


@pytest.mark.asyncio
async def test_invariant_no_continuation_with_an_output_less_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Randomised-order property over the scenario: every `create` is preceded by an output for every call of every
    batched response that finished before it."""
    import random

    monkeypatch.setattr(orl, "BATCH_STALL_S", 0.05)
    for seed in range(20):
        rnd = random.Random(seed)
        sess, sock = await _session()
        calls = [("c1", "record_field"), ("c2", "record_field"), ("c3", "lookup_knowledge")]
        await _feed(sock, _created("r1"), *[_call("r1", c, n) for c, n in calls], _done("r1"))
        order = [c for c, _ in calls]
        rnd.shuffle(order)
        drop = rnd.choice([None, *order])
        for c in order:
            if c != drop:
                await sess.send_tool_result(ToolCallResult(call_id=c, output={}))
                await asyncio.sleep(rnd.choice([0, 0.01]))
        await asyncio.sleep(0.15)
        ops = _ops(sock)
        first_create = ops.index("create")
        assert {f"out:{c}" for c, _ in calls} <= set(ops[:first_create]), (seed, ops)
        await sess.close()
