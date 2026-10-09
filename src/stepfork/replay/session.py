"""Deterministic frozen replay of recorded dependency boundaries.

Replay never iterates over events and prints them. It executes the agent's
local control flow and intercepts instrumented dependency boundaries
(``@trace_tool`` functions and ``llm_request`` calls), substituting captured
outputs while verifying that the live call sequence matches the recording.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Literal, Self

from stepfork.replay.exceptions import (
    RecordedDependencyError,
    ReplayError,
    ReplayExhaustedError,
    ReplayMismatchError,
    ReplayPolicyError,
)
from stepfork.replay.plan import RecordedCall, extract_recorded_calls
from stepfork.trace.canonical import canonical_json_bytes
from stepfork.trace.hashing import hash_json
from stepfork.trace.models import EventStatus, JsonValue, Trace
from stepfork.trace.redaction import redact_json
from stepfork.trace.replay_policy import ReplayPolicy

PREVIEW_LIMIT = 200

_current_replay: ContextVar[ReplaySession | None] = ContextVar(
    "stepfork_replay",
    default=None,
)


def active_replay() -> ReplaySession | None:
    """Return the replay session active in the current context, if any."""
    return _current_replay.get()


@dataclass(frozen=True)
class MatchedCall:
    """One recorded dependency call matched during replay."""

    index: int
    kind: Literal["tool", "llm"]
    label: str
    action: Literal["substituted", "executed"]


@dataclass(frozen=True)
class ReplayDecision:
    """How the caller should handle the current dependency call."""

    execute: bool
    value: JsonValue | None
    matched: MatchedCall


@dataclass(frozen=True)
class ReplaySummary:
    """Structured replay outcome for reporting."""

    mode: str
    matched: tuple[MatchedCall, ...]
    remaining: tuple[str, ...]


class ReplaySession:
    """Replay a recorded trace by intercepting dependency boundaries.

    Use as a context manager so the session is installed in the current
    context::

        with ReplaySession.from_trace("failure.sftrace", mode="frozen") as replay:
            result = run_agent()
    """

    def __init__(self, trace: Trace, *, mode: ReplayPolicy | str) -> None:
        self.trace = trace
        self.mode = ReplayPolicy(mode)
        self.calls: list[RecordedCall] = extract_recorded_calls(trace)
        self._cursor = 0
        self._matched: list[MatchedCall] = []
        self._token: Token[ReplaySession | None] | None = None
        self._entered = False

    @classmethod
    def from_trace(
        cls,
        path: str | Path | Trace,
        *,
        mode: ReplayPolicy | str = ReplayPolicy.FROZEN,
    ) -> ReplaySession:
        """Build a replay session from a `.sftrace` bundle or loaded trace."""
        trace = path if isinstance(path, Trace) else Trace.load(Path(path))
        return cls(trace, mode=mode)

    @property
    def matched(self) -> list[MatchedCall]:
        """Dependency calls matched so far, in call order."""
        return list(self._matched)

    @property
    def pending(self) -> int:
        """Number of recorded dependency calls not yet consumed."""
        return len(self.calls) - self._cursor

    @property
    def summary(self) -> ReplaySummary:
        """Structured summary of the replay session state."""
        return ReplaySummary(
            mode=self.mode.value,
            matched=tuple(self._matched),
            remaining=tuple(call.label for call in self.calls[self._cursor :]),
        )

    def __enter__(self) -> Self:
        if self._entered:
            raise ReplayError("ReplaySession cannot be re-entered")
        self._entered = True
        self._token = _current_replay.set(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        if self._token is not None:
            _current_replay.reset(self._token)
            self._token = None
        self._entered = False
        return False

    def before_tool(
        self,
        *,
        name: str,
        input: JsonValue,
    ) -> ReplayDecision:
        """Match and plan a tool call against the recorded sequence."""
        return self._dispatch("tool", name=name, model=None, provider=None, input=input)

    def before_llm(
        self,
        *,
        provider: str | None,
        model: str,
        input: JsonValue,
    ) -> ReplayDecision:
        """Match and plan an LLM call against the recorded sequence."""
        return self._dispatch(
            "llm",
            name=None,
            model=model,
            provider=provider,
            input=input,
        )

    def verify_complete(self) -> None:
        """Raise if recorded dependency calls remain unconsumed."""
        remaining = self.calls[self._cursor :]
        if not remaining:
            return
        labels = ", ".join(
            f"#{call.index + 1} {call.kind} {call.label}" for call in remaining[:5]
        )
        suffix = "" if len(remaining) <= 5 else f" (+{len(remaining) - 5} more)"
        raise ReplayMismatchError(
            f"replay ended before consuming {len(remaining)} recorded "
            f"dependency call(s): {labels}{suffix}"
        )

    def _dispatch(
        self,
        kind: Literal["tool", "llm"],
        *,
        name: str | None,
        model: str | None,
        provider: str | None,
        input: JsonValue,
    ) -> ReplayDecision:
        label = name if kind == "tool" else (model or "unknown-model")

        if self.mode is ReplayPolicy.FORBIDDEN:
            raise ReplayPolicyError(
                f"replay mode 'forbidden' rejects the {kind} call {label!r}"
            )
        if self.mode is ReplayPolicy.MANUAL:
            raise ReplayPolicyError(
                f"replay mode 'manual' requires approval before handling the "
                f"{kind} call {label!r}"
            )
        if self.mode is ReplayPolicy.DERIVED:
            raise ReplayPolicyError("replay mode 'derived' is not supported in v0.1")
        if not self._entered:
            raise ReplayError(
                "ReplaySession is not active; enter it with "
                "'with ReplaySession.from_trace(...)' before running the agent"
            )

        if self._cursor >= len(self.calls):
            actual_descriptor = _call_descriptor(
                kind=kind,
                name=name,
                model=model,
                provider=provider,
            )
            actual_fingerprint = _fingerprint(redact_json(input).value)
            raise ReplayExhaustedError(
                f"unexpected {kind} call {label!r}: all "
                f"{len(self.calls)} recorded dependency call(s) were already "
                f"consumed\n"
                f"  actual: {actual_descriptor}\n"
                f"  actual input fingerprint: {actual_fingerprint}"
            )

        position = self._cursor
        expected = self.calls[position]
        self._match_identity(
            expected,
            kind=kind,
            name=name,
            model=model,
            provider=provider,
            position=position,
        )
        self._match_input(expected, input=input, position=position)

        if expected.policy is ReplayPolicy.FORBIDDEN:
            raise ReplayPolicyError(
                f"recorded {kind} call {expected.label!r} forbids automatic replay"
            )
        if expected.policy is ReplayPolicy.MANUAL:
            raise ReplayPolicyError(
                f"recorded {kind} call {expected.label!r} requires manual "
                "approval before replay"
            )

        if expected.missing:
            raise ReplayMismatchError(
                f"no captured result for recorded {kind} call "
                f"{expected.label!r} at position {position + 1}"
            )
        self._verify_recorded_output_fingerprint(expected, position=position)

        self._cursor = position + 1
        matched = MatchedCall(
            index=position,
            kind=kind,
            label=expected.label,
            action="substituted" if self.mode is ReplayPolicy.FROZEN else "executed",
        )

        if self.mode is ReplayPolicy.LIVE:
            self._matched.append(matched)
            return ReplayDecision(execute=True, value=None, matched=matched)

        if expected.status is EventStatus.ERROR:
            self._matched.append(matched)
            raise RecordedDependencyError(
                kind=kind,
                name=expected.label,
                error_type=expected.error_type or "DependencyError",
                message=expected.error_message or "recorded dependency failure",
            )

        self._matched.append(matched)
        return ReplayDecision(
            execute=False,
            value=expected.output,
            matched=matched,
        )

    def _match_identity(
        self,
        expected: RecordedCall,
        *,
        kind: Literal["tool", "llm"],
        name: str | None,
        model: str | None,
        provider: str | None,
        position: int,
    ) -> None:
        position_label = position + 1
        actual_descriptor = _call_descriptor(
            kind=kind,
            name=name,
            model=model,
            provider=provider,
        )
        recorded_descriptor = _recorded_descriptor(expected)
        if expected.kind != kind:
            raise ReplayMismatchError(
                f"call #{position_label}: expected {expected.kind} "
                f"{expected.label!r} but the agent made a {kind} call "
                f"{name if kind == 'tool' else model!r}\n"
                f"  recorded: {recorded_descriptor}\n"
                f"  actual:   {actual_descriptor}"
            )
        if kind == "tool" and name != expected.name:
            raise ReplayMismatchError(
                f"call #{position_label}: expected tool {expected.label!r} "
                f"but the agent called {name!r}\n"
                f"  recorded: {recorded_descriptor}\n"
                f"  actual:   {actual_descriptor}"
            )
        if kind == "llm":
            recorded_model_fingerprint = _model_fingerprint(
                expected.provider,
                expected.model,
            )
            actual_model_fingerprint = _model_fingerprint(provider, model)
            if model != expected.model:
                raise ReplayMismatchError(
                    f"call #{position_label}: expected LLM model "
                    f"{expected.model!r} but the agent used {model!r}\n"
                    f"  recorded: {recorded_descriptor}\n"
                    f"  actual:   {actual_descriptor}\n"
                    f"  recorded model fingerprint: {recorded_model_fingerprint}\n"
                    f"  actual model fingerprint:   {actual_model_fingerprint}"
                )
            if provider != expected.provider:
                raise ReplayMismatchError(
                    f"call #{position_label}: expected provider "
                    f"{expected.provider!r} but the agent used {provider!r}\n"
                    f"  recorded: {recorded_descriptor}\n"
                    f"  actual:   {actual_descriptor}\n"
                    f"  recorded model fingerprint: {recorded_model_fingerprint}\n"
                    f"  actual model fingerprint:   {actual_model_fingerprint}"
                )

    def _match_input(
        self,
        expected: RecordedCall,
        *,
        input: JsonValue,
        position: int,
    ) -> None:
        sanitized = redact_json(input).value
        recorded_fingerprint = _recorded_input_fingerprint(expected)
        actual_fingerprint = _fingerprint(sanitized)
        if expected.input_hash is not None and expected.input_hash != _fingerprint(
            expected.input
        ):
            raise ReplayMismatchError(
                f"call #{position + 1}: recorded {expected.kind} "
                f"{expected.label!r} has an invalid input fingerprint\n"
                f"  recorded input fingerprint: {expected.input_hash}\n"
                f"  computed input fingerprint: {_fingerprint(expected.input)}\n"
                "  run `stepfork validate --verify-integrity` on the trace; "
                "legacy or tampered recordings cannot be used for strict replay"
            )
        try:
            matches = canonical_json_bytes(sanitized) == canonical_json_bytes(
                expected.input
            )
        except TypeError:
            matches = False
        if matches:
            return
        raise ReplayMismatchError(
            f"call #{position + 1}: {expected.kind} {expected.label!r} "
            "input diverged from the recording\n"
            f"  recorded input fingerprint: {recorded_fingerprint}\n"
            f"  actual input fingerprint:   {actual_fingerprint}\n"
            f"  recorded: {_preview(expected.input)}\n"
            f"  actual:   {_preview(sanitized)}"
        )

    def _verify_recorded_output_fingerprint(
        self,
        expected: RecordedCall,
        *,
        position: int,
    ) -> None:
        if expected.output_hash is None:
            return
        if expected.output_hash == _fingerprint(expected.output):
            return
        raise ReplayMismatchError(
            f"call #{position + 1}: recorded {expected.kind} "
            f"{expected.label!r} has an invalid output fingerprint\n"
            f"  recorded output fingerprint: {expected.output_hash}\n"
            f"  computed output fingerprint: {_fingerprint(expected.output)}\n"
            "  run `stepfork validate --verify-integrity` on the trace; "
            "legacy or tampered recordings cannot be used for strict replay"
        )


def _preview(value: JsonValue) -> str:
    """Return a short, sanitized, single-line preview of a JSON value."""
    try:
        text = canonical_json_bytes(value).decode("utf-8", errors="replace")
    except Exception:
        return "<unserializable>"
    if len(text) > PREVIEW_LIMIT:
        return f"{text[: PREVIEW_LIMIT - 1]}…"
    return text


def _fingerprint(value: JsonValue | None) -> str:
    if value is None:
        return "<none>"
    try:
        return hash_json(value)
    except Exception:
        return "<unavailable>"


def _recorded_input_fingerprint(expected: RecordedCall) -> str:
    if expected.input_hash is not None:
        return expected.input_hash
    computed = _fingerprint(expected.input)
    if computed == "<unavailable>":
        return "<legacy unavailable>"
    return f"{computed} (computed; recording had no stored input_hash)"


def _model_fingerprint(provider: str | None, model: str | None) -> str:
    return _fingerprint({"provider": provider, "model": model})


def _recorded_descriptor(expected: RecordedCall) -> str:
    if expected.kind == "tool":
        return f"tool name={expected.name!r}"
    return (
        f"llm provider={expected.provider!r} model={expected.model!r} "
        f"model_fingerprint={_model_fingerprint(expected.provider, expected.model)}"
    )


def _call_descriptor(
    *,
    kind: Literal["tool", "llm"],
    name: str | None,
    model: str | None,
    provider: str | None,
) -> str:
    if kind == "tool":
        return f"tool name={name!r}"
    return (
        f"llm provider={provider!r} model={model!r} "
        f"model_fingerprint={_model_fingerprint(provider, model)}"
    )
