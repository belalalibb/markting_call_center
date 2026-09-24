"""Latency option B: batched independent tool calls. Off by default (default path byte-identical: one
response.create per tool result); on → exactly one continuation per batch, after response.done and all results;
a call that never gets a result cannot stall the batch."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from qevion.adapters.providers import openai_realtime as orl
from qevion.contracts.provider import S2SSessionConfig, ToolCallResult
from qevion.core.instruction_composer import InstructionComposer
from qevion.main import _seed
from qevion.runtime.store import RuntimeStore


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


async def _session(batch: bool) -> tuple[Any, _Sock]:
    sock = _Sock()

    async def factory(url: str, headers: dict[str, str]) -> _Sock:
        return sock

    extra = {"parallel_tools": True} if batch else {}
    cfg = S2SSessionConfig(provider="openai_realtime", model="gpt-realtime", extra=extra)
    sess = await orl.OpenAIRealtimeAdapter(socket_factory=factory).open(cfg, credential="sk-test")
    return sess, sock


def _creates(sock: _Sock) -> int:
    return sum(1 for m in sock.sent if m["type"] == "response.create")


async def _feed(sock: _Sock, *msgs: dict[str, Any]) -> None:
    for m in msgs:
        sock.inbox.put_nowait(json.dumps(m))
    await asyncio.sleep(0.05)


def _call(cid: str) -> dict[str, Any]:
    return {
        "type": "response.function_call_arguments.done",
        "response_id": "r1",
        "call_id": cid,
        "name": "record_field",
        "arguments": "{}",
    }


@pytest.mark.asyncio
async def test_default_path_unchanged_one_create_per_result() -> None:
    sess, sock = await _session(batch=False)
    await _feed(sock, {"type": "response.created", "response": {"id": "r1"}}, _call("c1"), _call("c2"))
    await sess.send_tool_result(ToolCallResult(call_id="c1", output={}))
    await sess.send_tool_result(ToolCallResult(call_id="c2", output={}))
    await _feed(sock, {"type": "response.done", "response": {"id": "r1", "status": "completed"}})
    assert _creates(sock) == 2
    await sess.close()


@pytest.mark.asyncio
async def test_batch_one_continuation_after_done_and_all_results() -> None:
    sess, sock = await _session(batch=True)
    await _feed(sock, {"type": "response.created", "response": {"id": "r1"}}, _call("c1"), _call("c2"))
    await sess.send_tool_result(ToolCallResult(call_id="c1", output={}))
    await sess.send_tool_result(ToolCallResult(call_id="c2", output={}))
    assert _creates(sock) == 0  # response r1 not finished yet → no continuation (avoids active-response error)
    await _feed(sock, {"type": "response.done", "response": {"id": "r1", "status": "completed"}})
    assert _creates(sock) == 1
    await sess.close()


@pytest.mark.asyncio
async def test_batch_results_after_done_still_single_continuation() -> None:
    sess, sock = await _session(batch=True)
    await _feed(sock, {"type": "response.created", "response": {"id": "r1"}}, _call("c1"), _call("c2"))
    await _feed(sock, {"type": "response.done", "response": {"id": "r1", "status": "completed"}})
    await sess.send_tool_result(ToolCallResult(call_id="c1", output={}))
    assert _creates(sock) == 0  # c2 (independent, same batch) not answered yet
    await sess.send_tool_result(ToolCallResult(call_id="c2", output={}))
    assert _creates(sock) == 1
    await sess.close()


@pytest.mark.asyncio
async def test_unanswered_call_cannot_stall_the_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orl, "BATCH_STALL_S", 0.1)
    sess, sock = await _session(batch=True)
    await _feed(sock, {"type": "response.created", "response": {"id": "r1"}}, _call("c1"), _call("c2"))
    await sess.send_tool_result(ToolCallResult(call_id="c1", output={}))  # c2 = confirmation pending, no result
    await _feed(sock, {"type": "response.done", "response": {"id": "r1", "status": "completed"}})
    assert _creates(sock) == 0
    await asyncio.sleep(0.25)
    assert _creates(sock) == 1
    await sess.close()


def test_instruction_section_off_by_default_and_names_barriers() -> None:
    s = RuntimeStore()
    _seed(s)
    bp = next(r.blueprint for k, r in s.activities.items() if k.startswith("act_order_intake"))
    base = InstructionComposer(bp, s.tool_declarations).compose()
    assert "parallel_tools" not in base.sections
    on = InstructionComposer(bp, s.tool_declarations, options=frozenset({"parallel_tools"})).compose()
    txt = on.sections["parallel_tools"]
    assert "same response" in txt and "needs an earlier call's result" in txt
    assert {k: v for k, v in on.sections.items() if k != "parallel_tools"} == base.sections
