# Stepfork

Your agent failed. Make the failure a test.

Stepfork is a local-first, open source tool for behavioral regression testing
of AI agents. It records what an agent actually did during a run (every
external tool call, every LLM request, the final output), then turns the run
into a deterministic pytest regression test that encodes the corrected
behavior.

## The problem

AI agents fail in ways unit tests miss. A flight-search agent books the wrong
flight. A refund agent denies an eligible claim. When you diagnose such a
failure you usually hand-write a fix and hope the regression is covered.

## The Stepfork answer

```text
failed agent run
      ↓
record        capture tools, LLM calls, output, and failure
      ↓
inspect       review events, integrity, and error details
      ↓
frozen replay rerun the entrypoint without touching dependencies
      ↓
behavioral diff
      ↓
pytest regression test
```

- **Record** a buggy run into a portable `.sftrace` bundle, including runs
  that raise.
- **Replay** it with dependencies frozen: responses come from the recording, so
  no external service or tool body ever runs.
- **Diff** the buggy behavior against a corrected run to see exactly what
  changed.
- **Export** a pytest regression test that fails on the buggy code and passes
  on the fix.

Nothing is sent to a remote service. Traces, diffing, replay, and test export
all run locally.

## Key features

- Typed `.sftrace` v0.1 trace format with canonical JSON persistence
- Best-effort secret redaction
- SHA-256 integrity verification
- Frozen replay that never executes dependency bodies
- Behavioral diffing across equivalent dependency calls
- Executable pytest export with corrected expectations
- Python 3.11, 3.12, and 3.13 support

## Get started

Install, run a 60-second example, and learn the core workflow in the
[Getting started](getting-started.md) guide. The [examples](examples.md)
page walks through the three runnable demo agents in this repository.

## Explore

- [Concepts](concepts.md) - the vocabulary you need.
- [Recording](recording.md), [Replay](replay.md), [Diff](diff.md),
  [pytest export](pytest-export.md) - how each feature works.
- [Trace format](trace-format.md) - what a `.sftrace` bundle contains.
- [Security](security.md) - redaction, integrity checks, and their limits.
- [Troubleshooting](troubleshooting.md) - common errors and fixes.
- [Architecture](architecture.md), [Development](development.md) - for
  contributors.

Stepfork is experimental. See the
[changelog](https://github.com/utsab345/stepfork/blob/main/CHANGELOG.md) and
the [v0.1.0a1 release notes](releases/v0.1.0a1.md) for what shipped.