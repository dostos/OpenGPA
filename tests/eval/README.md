# Eval Scenarios

Adversarial rendering bug scenarios for OpenGPA's eval harness. Each scenario is a minimal GL/Vulkan application with one intentional rendering bug. Source files must not contain hint comments — the bug must be discoverable only through OpenGPA's tools.

## Naming Conventions
- `e-*.c` / `e-*.md` — synthetic scenarios written for this eval suite
- `r-*.c` / `r-*.md` — real-world bugs reproduced from public GitHub issues
- `s-*.c` / `s-*.md` — state-machine bugs mined from driver bug reports

## File Pairs
Each scenario has a `.c` source (the buggy app) and a `.md` description (ground-truth bug + expected diagnosis).

## See Also
- `src/python/gla/eval/README.md` — harness that runs these scenarios
- `scripts/capture-scenario.sh` — helper to capture a scenario trace
