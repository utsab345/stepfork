"""LLM client construction for the incident-triage case study.

Security notes
--------------
* This module never prints, logs, or returns credentials.
* When a Stepfork replay session is active (frozen or hybrid) we return a
  tripwire client. For frozen replay the OpenAI adapter never executes the
  client call, so the tripwire is never triggered; it exists to make an
  accidental live call fail loudly and to prevent minting a live access token
  during replay.

Supported live providers (selected with ``CASE_STUDY_LLM_PROVIDER``):

* ``gemini`` (default) - the Google Gemini API (AI Studio) OpenAI-compatible
  endpoint. Reads ``GEMINI_API_KEY`` (or ``GOOGLE_API_KEY``).
* ``vertex`` - Vertex AI OpenAI-compatible endpoint using Google Application
  Default Credentials (ADC).
* ``openai`` - the standard OpenAI API, or any OpenAI-compatible endpoint via
  ``OPENAI_BASE_URL``.

Nothing here is imported by the generated regression test at replay time
except through ``agent`` -> ``build_client`` which returns the tripwire.
"""

from __future__ import annotations

import os
from typing import Any

from counters import LIVE_LLM_ATTEMPTS


class TripwireClient:
    """A stand-in client that fails if any live completion is attempted."""

    def __init__(self) -> None:
        # Mirror the ``client.chat.completions.create`` attribute chain.
        self.chat = self
        self.completions = self

    def create(self, **kwargs: Any) -> Any:  # pragma: no cover - defensive
        LIVE_LLM_ATTEMPTS["count"] += 1
        raise RuntimeError(
            "live LLM call attempted while a Stepfork replay was active; "
            "frozen replay must never call the model"
        )


def _active_replay_session() -> Any:
    try:
        from stepfork.replay.session import active_replay
    except Exception:  # pragma: no cover - stepfork always present here
        return None
    return active_replay()


def build_client() -> Any:
    """Return a live client, or a tripwire when a frozen replay is active.

    Frozen replay must never reach the model, so it gets a tripwire. Hybrid
    replay intentionally re-runs selected LLM boundaries live while tools stay
    frozen, so it gets a real client.
    """
    session = _active_replay_session()
    if session is not None and not getattr(session, "hybrid", False):
        return TripwireClient()
    provider = os.environ.get("CASE_STUDY_LLM_PROVIDER", "gemini").strip().lower()
    if provider == "gemini":
        return _gemini_client()
    if provider == "openai":
        return _openai_client()
    if provider == "vertex":
        return _vertex_client()
    raise RuntimeError(
        f"unknown CASE_STUDY_LLM_PROVIDER {provider!r}; "
        "expected 'gemini', 'openai', or 'vertex'"
    )


def _gemini_client() -> Any:
    """Build an OpenAI-compatible client for the Google Gemini API."""
    from openai import OpenAI

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY (or GOOGLE_API_KEY) is not set; cannot create a live client"
        )
    base_url = os.environ.get(
        "GEMINI_OPENAI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    return OpenAI(api_key=api_key, base_url=base_url)


def _openai_client() -> Any:
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set; set it or use the vertex provider"
        )
    base_url = os.environ.get("OPENAI_BASE_URL")
    return OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)


def _vertex_client() -> Any:
    """Build an OpenAI-compatible client for the Vertex AI endpoint using ADC."""
    from openai import OpenAI

    try:
        import google.auth
        from google.auth.transport.requests import Request
    except ImportError as exc:  # pragma: no cover - setup error path
        raise RuntimeError(
            "google-auth is required for the vertex provider; "
            "install it with `uv pip install google-auth`"
        ) from exc

    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("CASE_STUDY_VERTEX_PROJECT")
    )
    location = (
        os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("CASE_STUDY_VERTEX_LOCATION")
        or "global"
    )

    credentials, detected_project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(Request())
    project = project or detected_project
    if not project:
        raise RuntimeError(
            "no Google Cloud project configured; set GOOGLE_CLOUD_PROJECT"
        )

    base_url = (
        f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
        f"/locations/{location}/endpoints/openapi"
    )
    # The OpenAI SDK uses api_key as the Bearer token. The token is short-lived
    # and stays in memory only.
    return OpenAI(api_key=credentials.token, base_url=base_url)
