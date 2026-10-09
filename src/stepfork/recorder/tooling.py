"""`@trace_tool`: capture tool boundaries during recording and replay."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar, cast, overload

from stepfork.recorder.session import RecordingSession, active_recorder
from stepfork.replay.session import ReplayDecision, active_replay
from stepfork.trace import JsonValue, ReplayPolicy, ToolCall
from stepfork.trace.jsonable import Serializer, to_json_value

P = ParamSpec("P")
R = TypeVar("R")


@overload
def trace_tool(func: Callable[P, R], /) -> Callable[P, R]: ...


@overload
def trace_tool(
    func: None = None,
    *,
    name: str | None = None,
    replay_policy: ReplayPolicy = ReplayPolicy.FROZEN,
    serializer: Serializer | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def trace_tool(
    func: Callable[P, R] | None = None,
    *,
    name: str | None = None,
    replay_policy: ReplayPolicy = ReplayPolicy.FROZEN,
    serializer: Serializer | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Record a tool call and its result inside an active recording.

    Outside a recording (and outside replay) the decorated function runs
    unchanged. During frozen replay the function body is not executed and the
    recorded result is returned instead.

    Supported forms::

        @trace_tool
        def search(destination: str) -> dict: ...

        @trace_tool(name="flight_search")
        def search(destination: str) -> dict: ...
    """

    def decorate(target: Callable[P, R]) -> Callable[P, R]:
        tool_name = name if name is not None else target.__name__
        if inspect.iscoroutinefunction(target):

            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                run = _ToolRun(
                    target=target,
                    tool_name=tool_name,
                    args=args,
                    kwargs=kwargs,
                    replay_policy=replay_policy,
                    serializer=serializer,
                )
                if run.passthrough:
                    return await cast(Awaitable[Any], target(*args, **kwargs))
                if run.substituted:
                    return run.substitute()
                try:
                    result = await cast(Awaitable[Any], target(*args, **kwargs))
                except BaseException as exc:
                    run.record_failure(exc)
                    raise
                else:
                    run.record_success(result)
                    return result
                finally:
                    run.close()

            return cast(
                Callable[P, R],
                functools.wraps(target)(async_wrapper),
            )

        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            run = _ToolRun(
                target=target,
                tool_name=tool_name,
                args=args,
                kwargs=kwargs,
                replay_policy=replay_policy,
                serializer=serializer,
            )
            if run.passthrough:
                return target(*args, **kwargs)
            if run.substituted:
                return cast(R, run.substitute())
            try:
                result = target(*args, **kwargs)
            except BaseException as exc:
                run.record_failure(exc)
                raise
            else:
                run.record_success(result)
                return result
            finally:
                run.close()

        return functools.wraps(target)(wrapper)

    if func is None:
        return decorate
    return decorate(func)


class _ToolRun:
    """One instrumented tool invocation shared by sync and async wrappers."""

    def __init__(
        self,
        *,
        target: Callable[..., Any],
        tool_name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        replay_policy: ReplayPolicy,
        serializer: Serializer | None,
    ) -> None:
        self.replay = active_replay()
        self.session: RecordingSession | None = None
        self.call: ToolCall | None = None
        self.decision: ReplayDecision | None = None
        self.input_json: JsonValue | None = None

        if self.replay is None and active_recorder() is None:
            return

        bound = _bind_arguments(target, args, kwargs)
        if self.replay is not None:
            self.input_json = to_json_value(bound, serializer=serializer)
            self.decision = self.replay.before_tool(
                name=tool_name,
                input=self.input_json,
            )
            return

        session = active_recorder()
        if session is None:  # pragma: no cover - defensive
            return
        self.session = session
        self.call = session.record_tool_call(
            name=tool_name,
            input=bound,
            replay_policy=replay_policy,
        )
        session.push_scope(self.call.id)

    @property
    def passthrough(self) -> bool:
        """True when neither recording nor replay is active."""
        return self.replay is None and self.session is None

    @property
    def substituted(self) -> bool:
        """True when replay returns a captured value instead of executing."""
        return self.decision is not None and not self.decision.execute

    def substitute(self) -> JsonValue | None:
        """Return the captured output for frozen replay."""
        if self.decision is None:  # pragma: no cover - defensive
            raise RuntimeError("no replay decision to substitute")
        return self.decision.value

    def record_success(self, result: Any) -> None:
        """Record the successful tool result when a session is active."""
        if self.session is None or self.call is None:
            return
        self.session.record_tool_result(self.call, result)

    def record_failure(self, exc: BaseException) -> None:
        """Record the failed tool result when a session is active."""
        if self.session is None or self.call is None:
            return
        self.session.record_tool_failure(self.call, exc)

    def close(self) -> None:
        """Leave the recording scope opened for this tool call."""
        if self.session is None or self.call is None:
            return
        self.session.pop_scope()


def _bind_arguments(
    target: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    try:
        bound = inspect.signature(target).bind(*args, **kwargs)
    except (TypeError, ValueError):
        return {"args": list(args), "kwargs": dict(kwargs)}
    bound.apply_defaults()
    arguments: dict[str, Any] = dict(bound.arguments)
    arguments.pop("self", None)
    arguments.pop("cls", None)
    return arguments
