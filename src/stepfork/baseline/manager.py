"""Storage and comparison for local named trace baselines."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from stepfork.diff import DiffResult, diff_traces
from stepfork.trace import RunEnd, RunStatus, Trace, TraceStorageError, validate_bundle
from stepfork.trace.integrity import INTEGRITY_FILE
from stepfork.trace.storage import REQUIRED_FILES

BASELINE_DIRECTORY = Path(".stepfork") / "baselines"
_BASELINE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_WINDOWS_RESERVED_NAMES = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
_BUNDLE_FILES = (*REQUIRED_FILES, INTEGRITY_FILE)


class BaselineError(ValueError):
    """Raised when a baseline cannot be stored, loaded, or compared."""


class BaselineExistsError(BaselineError):
    """Raised when saving would replace an existing named baseline."""


class BaselineNotFoundError(BaselineError):
    """Raised when a requested named baseline does not exist."""


class BaselineCompatibilityError(BaselineError):
    """Raised when a trace uses an unsupported bundle schema."""


@dataclass(frozen=True)
class Baseline:
    """A validated named baseline and its persisted trace path."""

    name: str
    path: Path
    trace: Trace


def save_baseline(
    name: str,
    trace_path: str | Path,
    *,
    directory: str | Path = BASELINE_DIRECTORY,
) -> Path:
    """Copy a valid trace into the local baseline store without overwriting."""
    _validate_name(name)
    source = Path(trace_path).expanduser()
    _load_verified_trace(source)

    root = _store_directory(directory)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BaselineError(f"cannot create baseline directory {root}: {exc}") from exc
    if root.is_symlink() or not root.is_dir():
        raise BaselineError(f"baseline path is not a directory: {root}")

    destination = root / f"{name}.sftrace"
    if destination.exists() or destination.is_symlink():
        raise BaselineExistsError(f"baseline {name!r} already exists at {destination}")

    try:
        destination.mkdir()
    except FileExistsError as exc:
        raise BaselineExistsError(
            f"baseline {name!r} already exists at {destination}"
        ) from exc
    except OSError as exc:
        raise BaselineError(f"cannot create baseline {destination}: {exc}") from exc

    try:
        for filename in _BUNDLE_FILES:
            shutil.copyfile(source / filename, destination / filename)
        _load_verified_trace(destination)
    except (BaselineError, OSError, TraceStorageError) as exc:
        shutil.rmtree(destination)
        if isinstance(exc, BaselineError):
            raise
        raise BaselineError(f"could not save baseline {name!r}: {exc}") from exc

    return destination


def load_baseline(
    name: str,
    *,
    directory: str | Path = BASELINE_DIRECTORY,
) -> Baseline:
    """Load and verify one named baseline."""
    _validate_name(name)
    root = _store_directory(directory)
    if root.is_symlink():
        raise BaselineError(f"baseline directory must not be a symlink: {root}")
    path = root / f"{name}.sftrace"
    if path.is_symlink():
        raise BaselineError(f"baseline must not be a symlink: {path}")
    if not path.exists():
        raise BaselineNotFoundError(f"baseline {name!r} was not found in {root}")
    return Baseline(name=name, path=path, trace=_load_verified_trace(path))


def list_baselines(
    *,
    directory: str | Path = BASELINE_DIRECTORY,
) -> list[Baseline]:
    """Return all valid named baselines in sorted order."""
    root = _store_directory(directory)
    if root.is_symlink():
        raise BaselineError(f"baseline directory must not be a symlink: {root}")
    if not root.exists():
        return []
    if not root.is_dir():
        raise BaselineError(f"baseline path is not a directory: {root}")

    baselines: list[Baseline] = []
    try:
        paths = sorted(root.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise BaselineError(f"cannot list baseline directory {root}: {exc}") from exc
    for path in paths:
        if path.name.endswith(".sftrace"):
            name = path.name[: -len(".sftrace")]
            baselines.append(load_baseline(name, directory=root))
    return baselines


def compare_baseline(
    name: str,
    candidate_path: str | Path,
    *,
    directory: str | Path = BASELINE_DIRECTORY,
) -> DiffResult:
    """Compare a candidate trace to a named, integrity-verified baseline."""
    baseline = load_baseline(name, directory=directory)
    candidate = Path(candidate_path).expanduser()
    candidate_trace = _load_verified_trace(candidate)
    result = diff_traces(baseline.trace, candidate_trace)
    return result.model_copy(
        update={
            "baseline": result.baseline.model_copy(update={"path": str(baseline.path)}),
            "candidate": result.candidate.model_copy(update={"path": str(candidate)}),
        }
    )


def _validate_name(name: str) -> None:
    if (
        not isinstance(name, str)
        or _BASELINE_NAME.fullmatch(name) is None
        or name.split(".", 1)[0] in _WINDOWS_RESERVED_NAMES
    ):
        raise BaselineError(
            "baseline name must be 1-64 lowercase letters, digits, dots, "
            "underscores, or hyphens, start with a letter or digit, and not "
            "be a reserved Windows device name"
        )


def _store_directory(directory: str | Path) -> Path:
    root = Path(directory).expanduser()
    if root.is_symlink():
        raise BaselineError(f"baseline directory must not be a symlink: {root}")
    if root.exists() and not root.is_dir():
        raise BaselineError(f"baseline path is not a directory: {root}")
    return root


def _load_verified_trace(path: Path) -> Trace:
    if path.is_symlink():
        raise BaselineError(f"trace bundle must not be a symlink: {path}")
    if not path.exists():
        raise BaselineNotFoundError(f"trace bundle was not found: {path}")
    if not path.is_dir():
        raise BaselineError(f"trace bundle is not a directory: {path}")

    for filename in _BUNDLE_FILES:
        file_path = path / filename
        if file_path.is_symlink():
            raise BaselineError(f"trace bundle file must not be a symlink: {file_path}")
        if not file_path.is_file():
            raise BaselineError(f"trace bundle is missing a regular file: {file_path}")

    try:
        result = validate_bundle(path, strict=True, verify_integrity=True)
    except OSError as exc:
        raise BaselineError(f"cannot read trace bundle {path}: {exc}") from exc
    if not result.valid:
        issues = "; ".join(f"{issue.code}: {issue.message}" for issue in result.issues)
        if any(issue.code == "unsupported_schema" for issue in result.issues):
            raise BaselineCompatibilityError(
                f"trace bundle uses an unsupported format: {issues}"
            )
        raise BaselineError(f"trace bundle is invalid: {issues}")

    try:
        trace = Trace.load(path)
    except (OSError, TraceStorageError) as exc:
        raise BaselineError(f"cannot load trace bundle {path}: {exc}") from exc
    run_ends = [event for event in trace.events if isinstance(event, RunEnd)]
    if (
        trace.status is RunStatus.RUNNING
        or len(run_ends) != 1
        or run_ends[0] is not trace.events[-1]
        or run_ends[0].run_status is not trace.status
    ):
        raise BaselineError(
            "trace bundle must contain one terminal run_end matching its run status"
        )
    return trace
