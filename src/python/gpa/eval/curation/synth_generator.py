"""Synthetic adversarial scenario generator.

Unlike Draft (which ports real upstream bugs), this generator fabricates
synthetic bugs from a (bug_class, capability) taxonomy.  No citation
requirement — the scenarios are adversarial by construction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

from gpa.eval.curation.llm_client import LLMClient
from gpa.eval.curation.prompts import load_prompt


@dataclass
class SynthRequest:
    scenario_id: str          # e.g. "e47_depth_precision_acne"
    bug_class: str            # e.g. "stencil mask leaked from a prior UI pass"
    capability: str           # e.g. "inspect_drawcall reveals stencil_test=true"
    difficulty: int           # 1-5
    adversarial_principles: list[str]  # short phrases


@dataclass
class SynthResult:
    scenario_id: str
    files: dict[str, str]


class SyntheticGenerator:
    """Produces synthetic OpenGL bug scenarios via an LLM.

    The LLM is prompted with a (bug_class, capability) pair and emits a pair
    of filename-marked fenced blocks (`main.c`, `scenario.md`).  We reuse
    Draft._parse_files for the parser but apply a looser validator that does
    NOT require an upstream citation.
    """

    def __init__(self, llm_client: LLMClient | Any):
        self._llm = llm_client
        self._system = load_prompt("synth_core_system")

    def generate(self, req: SynthRequest) -> SynthResult:
        user = (
            f"Scenario ID: {req.scenario_id}\n"
            f"Bug class: {req.bug_class}\n"
            f"Capability to exercise: {req.capability}\n"
            f"Difficulty: {req.difficulty}/5\n"
            "Adversarial principles: "
            + ", ".join(req.adversarial_principles)
            + "\n\nGenerate the scenario now.  Respond ONLY with the two "
              "filename-marked fenced blocks — no prose before or after."
        )
        resp = self._llm.complete(
            system=self._system,
            messages=[{"role": "user", "content": user}],
            max_tokens=8000,
        )

        # Reuse Draft._parse_files for the filename-marker format.
        from gpa.eval.curation.draft import Draft
        files = Draft._parse_files(resp.text)
        self._validate(files, req.scenario_id)
        return SynthResult(scenario_id=req.scenario_id, files=files)

    # ------------------------------------------------------------------
    # Validation

    @staticmethod
    def _validate(files: dict[str, str], scenario_id: str) -> None:
        """Loose validation for synthetic scenarios.

        Unlike Draft._validate, does NOT require upstream citations.  Enforces:
          - at least one .c source
          - scenario.md present with required sections
          - Bug Signature is well-formed YAML with `type` and `spec`
        """
        if not any(n.endswith(".c") for n in files):
            raise ValueError("no .c source file in synth output")
        if "scenario.md" not in files:
            raise ValueError("scenario.md missing from synth output")

        md = files["scenario.md"]
        required = [
            "## Bug",
            "## Expected",               # Expected Correct Output
            "## Actual",                 # Actual Broken Output
            "## Ground Truth Diagnosis",
            "## Difficulty",
            "## Adversarial Principles",
            "## How OpenGPA Helps",
            "## Tier",
            "## API",
            "## Framework",
            "## Bug Signature",
        ]
        for s in required:
            if s not in md:
                raise ValueError(f"scenario.md missing section: {s}")

        # Bug Signature must be well-formed YAML with 'type' and 'spec'.
        m_sig = re.search(
            r"##\s+Bug Signature\s*\n.*?```yaml\s*\n(.+?)\n```",
            md, re.DOTALL | re.IGNORECASE,
        )
        if not m_sig:
            raise ValueError("Bug Signature section missing or YAML block absent")
        try:
            parsed = yaml.safe_load(m_sig.group(1))
        except yaml.YAMLError as e:
            raise ValueError(f"Bug Signature YAML parse failed: {e}")
        if not isinstance(parsed, dict) or "type" not in parsed or "spec" not in parsed:
            raise ValueError("Bug Signature must have 'type' and 'spec' keys")
