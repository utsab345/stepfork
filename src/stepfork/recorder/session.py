"""Recording sessions that capture agent executions as `.sftrace` traces."""

from __future__ import annotations

import asyncio
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, TypeVar

from stepfork.replay.session import active_replay
from stepfork.trace import (
    ErrorEvent,
    EventBase,
    EventStatus,
    EventType,
    FailureInfo,
    JsonValue,
    LLMRequest,
    LLMResponse,
    ReplayPolicy,
    RunEnd,
    RunStart,
    RunStatus,
    StateChange,
    ToolCall,
    ToolResult,
    Trace,
    TraceSerializationError,
    save_trace,
)
from stepfork.trace.jsonable import Serializer, to_json_value
from stepfork.trace.manifest import EnvironmentInfo, TraceTotals
from stepfork.version import __version__

DEFAULT_TRACE_DIR = Path(".stepfork") / "traces"

E = TypeVar("E", bound=EventBase)

_current_recorder: ContextVar[RecordingSession | None] = ContextVar(
    "stepfork_recording",
    default=None,
)


def active_recorder() -> RecordingSession | None:
    """Return the recording session active in the current context, if any."""
    return _current_recorder.get()


class RecordingSession:
    """Capture LLM, tool, and state events for one agent run.

    Enter the session as a context manager; the trace is persisted when the
    block exits and any application exception is always preserved::

        with record("booking-agent", output="failure.sftrace") as session:
            result = run_agent()
            session.set_output(result)
    """

    def __init__(
        self,
        agent_name: str,
        *,
        output: str | Path | None = None,
        overwrite: bool = False,
        serializer: Serializer | None = None,
        run_input: Any = None,
    ) -> None:
        self.trace = Trace(
            agent_name=agent_name,
            environment=EnvironmentInfo(
                python=f"{sys.version_info.major}.{sys.version_info.minor}",
                os=sys.platform,
                stepfork_version=__version__,
            ),
        )
        self._serializer = serializer
        self._run_input = run_input
        self._output_path = (
            Path(output)
            if output is not None
            else _default_output_path(agent_name, self.trace.run_id)
        )
        self._overwrite = overwrite
        self._scope: ContextVar[tuple[str, ...]] = ContextVar(
            f"stepfork_recording_scope_{self.trace.run_id}", default=()
        )
        self._scope_token: Token[tuple[str, ...]] | None = None
        self._token: Token[RecordingSession | None] | None = None
        self._started = False
        self._finished = False
        self._inert = False
        self._pending_output: JsonValue | None = None
        self._has_output = False
        self.path: Path | None = None

    @property
    def agent_name(self) -> str:
        """Name of the recorded agent."""
        return self.trace.agent_name

    @property
    def run_id(self) -> str:
        """Opaque run identifier for this recording."""
        return self.trace.run_id

    @property
    def output_path(self) -> Path:
        """Where the trace bundle will be (or was) written."""
        return self._output_path

    def to_json(self, value: Any) -> JsonValue:
        """Convert a runtime value into a JSON trace payload."""
        return to_json_value(value, serializer=self._serializer)

    def __enter__(self) -> RecordingSession:
        if self._started:
            raise RuntimeError("RecordingSession cannot be re-entered")
        self._started = True
        token = _current_recorder.set(self)
        try:
            if active_replay() is not None:
                # Frozen replay: agent entrypoints keep their record() blocks.
                # Stay inert so replay never writes a new trace bundle.
                self._inert = True
                self._scope_token = self._scope.set(())
                self._token = token
                return self
            if self._run_input is None:
                start = self.trace.add(RunStart())
            else:
                start = self.trace.add(RunStart(input=self.to_json(self._run_input)))
        except BaseException:
            _current_recorder.reset(token)
            raise
        self._scope_token = self._scope.set((start.id,))
        self._token = token
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        try:
            if self._inert:
                return False
            if not self._finished:
                self._finalize(exc)
                self._finished = True
                self.path = save_trace(
                    self.trace,
                    self._output_path,
                    overwrite=self._overwrite,
                )
        except Exception as save_error:
            if exc is None:
                raise
            exc.add_note(f"stepfork: trace was not saved: {save_error}")
        finally:
            if self._token is not None:
                _current_recorder.reset(self._token)
                self._token = None
            if self._scope_token is not None:
                self._scope.reset(self._scope_token)
                self._scope_token = None
        return False

    async def __aenter__(self) -> RecordingSession:
        """Enter a recording in the current async task."""
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        """Persist the trace without blocking the event loop on disk I/O."""
        try:
            if not self._inert and not self._finished:
                self._finalize(exc)
                self._finished = True
                self.path = await asyncio.to_thread(
                    save_trace, self.trace, self._output_path, overwrite=self._overwrite
                )
        except Exception as save_error:
            if exc is None:
                raise
            exc.add_note(f"stepfork: trace was not saved: {save_error}")
        finally:
            if self._token is not None:
                _current_recorder.reset(self._token)
                self._token = None
            if self._scope_token is not None:
                self._scope.reset(self._scope_token)
                self._scope_token = None
        return False

    def push_scope(self, event_id: str) -> None:
        """Make ``event_id`` the parent scope for subsequently recorded events."""
        if self._inert:
            return
        self._scope.set((*self._scope.get(), event_id))

    def pop_scope(self) -> None:
        """Leave the current dependency scope."""
        if self._inert:
            return
        stack = self._scope.get()
        if len(stack) <= 1:
            raise RuntimeError("cannot leave the root recording scope")
        self._scope.set(stack[:-1])

    def record_llm_request(
        self,
        *,
        model: str,
        input: Any,
        provider: str | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.FROZEN,
    ) -> LLMRequest:
        """Record an outgoing LLM request."""
        event = LLMRequest(
            model=model,
            input=self.to_json(input),
            provider=provider,
            replay_policy=replay_policy,
        )
        return self._append(event)

    def record_llm_response(
        self,
        request: LLMRequest,
        output: Any,
        *,
        model: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        cost_usd: float | None = None,
    ) -> LLMResponse:
        """Record the LLM response paired with ``request``."""
        event = LLMResponse(
            model=model if model is not None else request.model,
            output=self.to_json(output),
            duration_ms=_elapsed_ms(request.timestamp),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            parent_id=request.id,
        )
        return self._append(event)

    def record_tool_call(
        self,
        *,
        name: str,
        input: Any,
        replay_policy: ReplayPolicy = ReplayPolicy.FROZEN,
    ) -> ToolCall:
        """Record an outgoing tool call."""
        event = ToolCall(
            name=name,
            input=self.to_json(input),
            replay_policy=replay_policy,
        )
        return self._append(event)

    def record_tool_result(
        self,
        call: ToolCall,
        output: Any,
        *,
        status: EventStatus = EventStatus.OK,
    ) -> ToolResult:
        """Record the result paired with ``call``."""
        event = ToolResult(
            name=call.name,
            output=self.to_json(output),
            duration_ms=_elapsed_ms(call.timestamp),
            status=status,
            parent_id=call.id,
        )
        return self._append(event)

    def record_tool_failure(self, call: ToolCall, exc: BaseException) -> ToolResult:
        """Record a failed tool result and a linked error event for ``exc``."""
        error_type = type(exc).__name__
        message = str(exc) or error_type
        result = self._append(
            ToolResult(
                name=call.name,
                output={"error_type": error_type, "message": message},
                duration_ms=_elapsed_ms(call.timestamp),
                status=EventStatus.ERROR,
                parent_id=call.id,
            )
        )
        self._append(
            ErrorEvent(
                error_type=error_type,
                message=message,
                parent_id=result.id,
            )
        )
        return result

    def record_llm_failure(self, request: LLMRequest, exc: BaseException) -> ErrorEvent:
        """Record a failed LLM call linked to ``request``."""
        error_type = type(exc).__name__
        message = str(exc) or error_type
        return self._append(
            ErrorEvent(
                error_type=error_type,
                message=message,
                parent_id=request.id,
            )
        )

    def record_state_change(
        self,
        *,
        key: str | None = None,
        before: Any = None,
        after: Any = None,
    ) -> StateChange:
        """Record a change to agent state."""
        event = StateChange(
            key=key,
            before=self.to_json(before),
            after=self.to_json(after),
        )
        return self._append(event)

    def record_error(
        self,
        error_type: str,
        message: str,
        *,
        details: Any = None,
        parent_id: str | None = None,
    ) -> ErrorEvent:
        """Record an error event in the current scope."""
        event = ErrorEvent(
            error_type=error_type,
            message=message or error_type,
            details=self.to_json(details) if details is not None else None,
            parent_id=parent_id,
        )
        return self._append(event)

    def set_output(self, value: Any) -> None:
        """Set the final run output recorded in ``run_end``."""
        self._pending_output = self.to_json(value)
        self._has_output = True

    @contextmanager
    def llm_call(
        self,
        *,
        model: str,
        input: Any,
        provider: str | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.FROZEN,
    ) -> Iterator[LLMCallHandle]:
        """Manually record an LLM call around a ``with`` body.

        This API records during :func:`record` sessions. Replayable agents
        should prefer :func:`stepfork.llm_request`, which substitutes captured
        responses during frozen replay instead of executing the body.
        """
        request = self.record_llm_request(
            model=model,
            input=input,
            provider=provider,
            replay_policy=replay_policy,
        )
        handle = LLMCallHandle(request)
        self.push_scope(request.id)
        try:
            yield handle
        except BaseException as exc:
            self.record_llm_failure(request, exc)
            raise
        finally:
            self.pop_scope()
        self.record_llm_response(
            request,
            handle.output,
            model=handle.model,
            prompt_tokens=handle.prompt_tokens,
            completion_tokens=handle.completion_tokens,
            total_tokens=handle.total_tokens,
            cost_usd=handle.cost_usd,
        )

    def _append(self, event: E) -> E:
        if self._finished:
            raise RuntimeError("recording session has already finished")
        scope = self._scope.get()
        if event.parent_id is None and scope:
            event = event.model_copy(update={"parent_id": scope[-1]})
        return self.trace.add(event)

    def _finalize(self, exc: BaseException | None) -> None:
        output: JsonValue | None = None
        failure: FailureInfo | None = None

        if exc is not None:
            error_type = type(exc).__name__
            message = str(exc) or error_type
            error_event = self.record_error(error_type, message)
            failure = FailureInfo(
                type=error_type,
                message=message,
                step=error_event.step,
            )
            status = RunStatus.FAILED
        else:
            status = RunStatus.COMPLETED
            if self._has_output:
                output = self._pending_output

        run_end = self.trace.add(RunEnd(run_status=status, output=output))
        duration_ms = max(
            0,
            int((run_end.timestamp - self.trace.created_at).total_seconds() * 1000),
        )
        self.trace.totals = TraceTotals(
            events=len(self.trace.events),
            llm_calls=sum(
                event.type.value == "llm_request" for event in self.trace.events
            ),
            tool_calls=sum(
                event.type.value == "tool_call" for event in self.trace.events
            ),
            cost_usd=_total_cost(self.trace),
            duration_ms=duration_ms,
        )
        self.trace.status = status
        self.trace.failure = failure


class LLMCallHandle:
    """Mutable handle yielded by :meth:`RecordingSession.llm_call`."""

    def __init__(self, request: LLMRequest) -> None:
        self.request = request
        self.model: str | None = request.model
        self.output: Any = None
        self.prompt_tokens: int | None = None
        self.completion_tokens: int | None = None
        self.total_tokens: int | None = None
        self.cost_usd: float | None = None

    def set_output(
        self,
        value: Any,
        *,
        model: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        cost_usd: float | None = None,
    ) -> None:
        """Attach the response payload and optional usage metadata."""
        self.output = value
        if model is not None:
            self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.cost_usd = cost_usd


def record(
    agent_name: str,
    *,
    output: str | Path | None = None,
    overwrite: bool = False,
    serializer: Serializer | None = None,
    run_input: Any = None,
) -> RecordingSession:
    """Create a recording session for one agent run.

    When ``output`` is omitted the trace is written under
    ``.stepfork/traces/``. The session persists the trace on exit, including
    when the recorded block raises, and always re-raises the original error.

    Inside an active replay the session is inert: the block runs, but no
    trace is recorded or written, so replaying an entrypoint never creates
    new bundles.
    """
    return RecordingSession(
        agent_name,
        output=output,
        overwrite=overwrite,
        serializer=serializer,
        run_input=run_input,
    )


def _elapsed_ms(since: datetime) -> int:
    return max(0, int((datetime.now(UTC) - since).total_seconds() * 1000))


def _total_cost(trace: Trace) -> float | None:
    costs = [
        event.cost_usd
        for event in trace.events
        if event.type is EventType.LLM_RESPONSE
        and isinstance(event, LLMResponse)
        and event.cost_usd is not None
    ]
    if not costs:
        return None
    return sum(costs)


def _default_output_path(agent_name: str, run_id: str) -> Path:
    safe_agent = re.sub(r"[^A-Za-z0-9._-]+", "-", agent_name).strip("-") or "agent"
    return DEFAULT_TRACE_DIR / f"{safe_agent}-{run_id}.sftrace"


__all__ = [
    "DEFAULT_TRACE_DIR",
    "LLMCallHandle",
    "RecordingSession",
    "TraceSerializationError",
    "active_recorder",
    "record",
]
