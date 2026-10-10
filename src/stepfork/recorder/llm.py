"""Provider-independent LLM boundary recording and replay."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from stepfork.recorder.session import active_recorder
from stepfork.replay.session import active_replay
from stepfork.trace import ReplayPolicy
from stepfork.trace.jsonable import Serializer, to_json_value


def llm_request(
    *,
    model: str,
    input: Any,
    call: Callable[[], Any],
    provider: str | None = None,
    replay_policy: ReplayPolicy = ReplayPolicy.FROZEN,
    serializer: Serializer | None = None,
) -> Any:
    """Invoke an LLM dependency while recording or replaying its boundary.

    ``call`` is a zero-argument callable performing the real request. Its
    behavior depends on the active Stepfork context:

    - recording (``with record(...)``): the request and response are captured
      and ``call()`` executes.
    - frozen replay: ``call()`` is **not** executed; the recorded response is
      returned.
    - live replay: the call matches the recording, then ``call()`` executes.
    - no active context: ``call()`` executes unchanged.

    This is the replay-safe way for agents to wrap LLM calls.
    """
    replay = active_replay()
    if replay is not None:
        input_json = to_json_value(input, serializer=serializer)
        decision = replay.before_llm(
            provider=provider,
            model=model,
            input=input_json,
        )
        if not decision.execute:
            return decision.value
        return call()

    session = active_recorder()
    if session is None:
        return call()

    request = session.record_llm_request(
        model=model,
        input=input,
        provider=provider,
        replay_policy=replay_policy,
    )
    session.push_scope(request.id)
    try:
        output = call()
    except BaseException as exc:
        session.record_llm_failure(request, exc)
        raise
    finally:
        session.pop_scope()
    session.record_llm_response(request, output, model=model)
    return output


async def allm_request(
    *,
    model: str,
    input: Any,
    call: Callable[[], Awaitable[Any]],
    provider: str | None = None,
    replay_policy: ReplayPolicy = ReplayPolicy.FROZEN,
    serializer: Serializer | None = None,
) -> Any:
    """Async LLM boundary with the same strict frozen matching as ``llm_request``."""
    replay = active_replay()
    if replay is not None:
        input_json = to_json_value(input, serializer=serializer)
        decision = replay.before_llm(provider=provider, model=model, input=input_json)
        if not decision.execute:
            return decision.value
        return await call()

    session = active_recorder()
    if session is None:
        return await call()

    request = session.record_llm_request(
        model=model, input=input, provider=provider, replay_policy=replay_policy
    )
    session.push_scope(request.id)
    try:
        output = await call()
    except BaseException as exc:
        session.record_llm_failure(request, exc)
        raise
    finally:
        session.pop_scope()
    session.record_llm_response(request, output, model=model)
    return output
