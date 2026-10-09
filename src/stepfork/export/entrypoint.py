"""Trusted resolution of ``MODULE:FUNCTION`` entrypoints.

Stepfork only imports entrypoints the user passes explicitly on the command
line or in API calls. Trace bundles are data and are never imported, evaluated,
or executed.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast


class EntrypointError(ValueError):
    """Raised when an entrypoint specification cannot be resolved."""


def resolve_entrypoint(
    spec: str,
    *,
    import_root: Path | None = None,
) -> Callable[[], Any]:
    """Import ``MODULE:FUNCTION`` and return the zero-argument callable.

    ``import_root`` (when given) is prepended to ``sys.path`` so local
    project modules such as ``examples.booking_agent`` resolve regardless of
    how Python was started.
    """
    module_name, separator, attribute_path = spec.partition(":")
    if not separator or not module_name or not attribute_path:
        raise EntrypointError(
            f"invalid entrypoint {spec!r}; expected the form MODULE:FUNCTION"
        )

    if import_root is not None:
        root = str(import_root)
        if root not in sys.path:
            sys.path.insert(0, root)

    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise EntrypointError(
            f"cannot import module {module_name!r}: {type(exc).__name__}: {exc}"
        ) from exc

    target: Any = module
    for part in attribute_path.split("."):
        if not hasattr(target, part):
            raise EntrypointError(f"module {module_name!r} has no attribute {part!r}")
        target = getattr(target, part)

    if not callable(target):
        raise EntrypointError(f"entrypoint {spec!r} is not callable")
    return cast("Callable[[], Any]", target)
