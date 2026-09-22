"""Conversation context primitives (§21 QV-CTX, §22 QV-CI): Entity Focus Stack and Pending Objectives.

Generic: entities are opaque (id, type); objectives are opaque strings + kinds. No business vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass
class FocusEntry:
    entity_id: str
    entity_type: str
    ts_ms: int
    source: str = "user"  # user | tool | knowledge | system
    label: str | None = None


@dataclass
class EntityFocusStack:
    """Most-recent-first stack used to resolve references like 'that one' / 'the second' / 'it'."""

    max_depth: int = 8
    _stack: list[FocusEntry] = field(default_factory=list)

    def push(
        self, entity_id: str, entity_type: str, ts_ms: int, *, source: str = "user", label: str | None = None
    ) -> FocusEntry:
        self._stack = [e for e in self._stack if e.entity_id != entity_id]
        entry = FocusEntry(entity_id, entity_type, ts_ms, source, label)
        self._stack.insert(0, entry)
        del self._stack[self.max_depth :]
        return entry

    def current(self, entity_type: str | None = None) -> FocusEntry | None:
        for e in self._stack:
            if entity_type is None or e.entity_type == entity_type:
                return e
        return None

    def nth(self, n: int, entity_type: str | None = None) -> FocusEntry | None:
        """1-based position among recent entities of a type ('the second one')."""
        items = [e for e in self._stack if entity_type is None or e.entity_type == entity_type]
        return items[n - 1] if 0 < n <= len(items) else None

    def candidates(self, entity_type: str | None = None) -> list[FocusEntry]:
        return [e for e in self._stack if entity_type is None or e.entity_type == entity_type]

    def is_ambiguous(self, entity_type: str | None = None, window: int = 2) -> bool:
        """True when ≥2 same-type entities were mentioned recently → Core should ASK_CLARIFYING_QUESTION."""
        return len(self.candidates(entity_type)[:window]) >= 2

    def clear(self) -> None:
        self._stack.clear()


class ObjectiveKind(StrEnum):
    COLLECT_FIELD = "collect_field"
    ANSWER_QUESTION = "answer_question"
    CONFIRM = "confirm"
    EXECUTE_TOOL = "execute_tool"
    RESOLVE_AMBIGUITY = "resolve_ambiguity"
    DELIVER_DISCLOSURE = "deliver_disclosure"
    CLOSE = "close"


@dataclass
class Objective:
    kind: ObjectiveKind
    ref: str  # field name / question id / tool call id / disclosure ref
    priority: int = 100  # lower = sooner
    created_ms: int = 0
    attempts: int = 0
    note: str | None = None


@dataclass
class PendingObjectives:
    """Multi-intent + topic-switch support (X² §22–23): park what the user raised, come back in priority order."""

    _items: list[Objective] = field(default_factory=list)
    max_attempts: int = 3

    def add(
        self, kind: ObjectiveKind, ref: str, *, priority: int = 100, ts_ms: int = 0, note: str | None = None
    ) -> Objective:
        for o in self._items:
            if o.kind == kind and o.ref == ref:
                return o
        obj = Objective(kind, ref, priority, ts_ms, 0, note)
        self._items.append(obj)
        self._items.sort(key=lambda o: (o.priority, o.created_ms))
        return obj

    def peek(self) -> Objective | None:
        return self._items[0] if self._items else None

    def attempt(self) -> Objective | None:
        """Take the top objective for another try; drop it (and report) when attempts are exhausted."""
        top = self.peek()
        if top is None:
            return None
        top.attempts += 1
        return top

    def exhausted(self) -> list[Objective]:
        return [o for o in self._items if o.attempts >= self.max_attempts]

    def complete(self, kind: ObjectiveKind, ref: str) -> bool:
        before = len(self._items)
        self._items = [o for o in self._items if not (o.kind == kind and o.ref == ref)]
        return len(self._items) != before

    def has(self, kind: ObjectiveKind, ref: str | None = None) -> bool:
        return any(o.kind == kind and (ref is None or o.ref == ref) for o in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def snapshot(self) -> list[tuple[str, str, int]]:
        return [(o.kind.value, o.ref, o.attempts) for o in self._items]
