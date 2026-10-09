# Terminal demo

A reproducible terminal recording of the failure-to-test workflow, driven by
the [VHS](https://github.com/charmbracelet/vhs) tape recorder.

- `stepfork-demo.tape` - the recording script.
- `stepfork-demo.gif` - the rendered output, committed so it can be embedded
  and re-recorded identically.

## What the demo shows

1. `stepfork --version`.
2. The quickstart agent source (`examples/quickstart/agent.py`).
3. The full failure-to-test demo:
   record the buggy run, record the corrected run, validate with integrity,
   freeze-replay without executing the dependency, diff the behavior, and
   generate a pytest regression test that fails on the buggy agent and passes
   on the fixed one.
4. `stepfork replay` and `stepfork diff` directly from the CLI.

## Requirements

- [VHS](https://github.com/charmbracelet/vhs) (a single binary)
- [ttyd](https://github.com/tsl0922/ttyd/releases) (VHS terminal backend)
- [ffmpeg](https://ffmpeg.org/) (GIF encoding)
- `uv` with the Stepfork dev dependencies synced (`uv sync`)

## Record

From the repository root:

```bash
export PATH="$(pwd)/.venv/bin:$PATH"
vhs scripts/terminal-demo/stepfork-demo.tape
```

The tape writes `scripts/terminal-demo/stepfork-demo.gif` and prints tips
hosted at `vhs publish <file>.gif` for sharing.

## Validate the output

```bash
file scripts/terminal-demo/stepfork-demo.gif
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames \
  -of default=noprint_wrappers=1 scripts/terminal-demo/stepfork-demo.gif
```

The demo ends with `DEMO COMPLETE: failure -> frozen trace -> regression test`
and `buggy agent: FAIL (rc=1), fixed agent: PASS`.