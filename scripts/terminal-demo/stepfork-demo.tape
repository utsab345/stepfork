# Stepfork failure-to-test terminal demo.
#
# Record with (see README.md for dependency setup):
#   vhs scripts/terminal-demo/stepfork-demo.tape
#
# Run from the repository root, with the project virtualenv on PATH so the
# `stepfork` CLI resolves:
#   export PATH="$(pwd)/.venv/bin:$PATH"

Output scripts/terminal-demo/stepfork-demo.gif
Set FontSize 14
Set Width 120
Set Height 34
Set Padding 14
Set Margin 2
Set Framerate 24

Type "stepfork --version"
Enter
Sleep 1s

Type "cat examples/quickstart/agent.py"
Enter
Sleep 4s

Type "uv run python examples/quickstart/demo.py"
Enter
Sleep 8s

Type "stepfork replay examples/quickstart/.artifacts/quickstart_failure.sftrace --entrypoint examples.quickstart:run_agent --mode frozen"
Enter
Sleep 5s

Type "stepfork diff examples/quickstart/.artifacts/quickstart_failure.sftrace examples/quickstart/.artifacts/quickstart_fixed.sftrace"
Enter
Sleep 4s