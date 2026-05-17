# Scripts

Helper scripts for OpenGPA development, CI, and eval workflows.

## Key Files
- `setup-headless.sh` — installs Xvfb, Mesa, and other headless GL dependencies
- `start-eval-server.sh` — starts the OpenGPA REST API server in eval mode
- `capture-scenario.sh` — runs a single eval scenario under the GL shim and saves the trace
- `capture-all-scenarios.sh` — batch-captures all scenarios in `tests/eval/`
- `run-multi-model-eval.py` — drives the eval harness across multiple LLM models and writes a comparison report
- `run-eval-claude-code.sh` — runs the eval using Claude Code as the agent

## See Also
- `src/python/bhdr/eval/README.md` — eval harness invoked by these scripts
- `tests/eval/README.md` — scenarios captured and evaluated
