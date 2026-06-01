"""hlab review — pre-run structural review of a v1 experiment.

Produces a PASS / WARN / ERROR verdict per docs/cli.md §5 and the validation
rules in docs/experiment-yaml-schema.md §18. Read-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agent_harness_lab.experiment_spec import (
    ERROR,
    WARN,
    ExperimentSpecError,
    Problem,
    parse_experiment_yaml,
    validate_spec,
)

PASS = "PASS"


@dataclass
class ReviewReport:
    experiment_dir: Path
    verdict: str  # PASS | WARN | ERROR
    problems: list[Problem] = field(default_factory=list)

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self.problems if p.level == ERROR]

    @property
    def warnings(self) -> list[Problem]:
        return [p for p in self.problems if p.level == WARN]


def review_experiment(experiment_dir: Path) -> ReviewReport:
    """Review an experiment directory. Never raises for ordinary problems —
    a missing/invalid experiment.yaml is reported as an ERROR verdict."""
    yaml_path = experiment_dir / "experiment.yaml"
    if not yaml_path.exists():
        return ReviewReport(
            experiment_dir, ERROR,
            [Problem(ERROR, "experiment_yaml_missing",
                     "experiment.yaml not found in experiment directory")],
        )
    try:
        spec = parse_experiment_yaml(yaml_path)
    except ExperimentSpecError as e:
        return ReviewReport(
            experiment_dir, ERROR,
            [Problem(ERROR, "experiment_yaml_invalid", str(e))],
        )

    problems = validate_spec(spec, experiment_dir)
    if any(p.level == ERROR for p in problems):
        verdict = ERROR
    elif any(p.level == WARN for p in problems):
        verdict = WARN
    else:
        verdict = PASS
    return ReviewReport(experiment_dir, verdict, problems)
