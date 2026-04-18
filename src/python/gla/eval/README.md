# Eval Harness

Eval harness for OpenGPA. Measures how effectively an LLM agent can diagnose rendering bugs using OpenGPA's tools. Loads scenarios, drives an agent through a debug session, scores the diagnosis, and writes a report.

## Key Files
- `loader.py` — loads scenario definitions from `tests/eval/`
- `agent.py` — drives an LLM agent (Claude or other) through the scenario
- `scorer.py` — compares agent diagnosis to the ground-truth bug description
- `reporter.py` — writes per-run and aggregate reports

## See Also
- `tests/eval/README.md` — scenario source files
- `scripts/run-multi-model-eval.py` — top-level eval runner script
