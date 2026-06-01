"""Agent Harness Lab — `hlab` command-line entry (v1).

Six public commands: init / new / review / run / status / report.
This layer parses args, prints results, and delegates to scaffold / reviewer /
experiment_spec. The old v0.10 engine modules (workflow.py, runner.py, ...)
remain in the package as internal implementation reused by later phases; they
are no longer exposed as CLI commands.

Phase 1 scope: init, new, review, status are fully implemented; run and report
validate and report a clear "implemented in a later phase" boundary (AutoRunner,
CopilotTaskRenderer, ReportBuilder are not built yet).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent_harness_lab import copilot, scaffold
from agent_harness_lab.experiment_spec import (
    ExperimentSpecError,
    load_agent_runtime_spec,
    load_cases,
    parse_experiment_yaml,
)

_COLLECTION_KEYS = ("traces", "raw", "artifacts", "snapshots", "scores")
_REVIEW_KEYS = ("artifact_review", "skill_review", "memory_review", "context_review")
from agent_harness_lab.reviewer import ERROR, PASS, WARN, review_experiment


def _utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # Windows: force UTF-8


def _resolve_experiment(arg: str) -> Path | None:
    """Accept `experiments/<name>`, an absolute/relative dir, or a bare `<name>`."""
    if not arg or not arg.strip():
        return None  # empty arg must be 'not found', not the cwd
    # a bare name (no path separator) resolves to experiments/<name> first, so a
    # same-named directory in the CWD cannot shadow the real experiment
    if "/" not in arg and "\\" not in arg:
        named = Path.cwd() / "experiments" / arg
        if named.is_dir():
            return named
    p = Path(arg)
    if p.is_dir():
        return p
    cand = Path.cwd() / "experiments" / arg
    if cand.is_dir():
        return cand
    return None


# --- commands ----------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:
    root = Path.cwd()
    blocked = [m for m in ("experiments", ".hlab")
               if (root / m).exists() and not (root / m).is_dir()]
    if blocked:
        # The layout cannot be completed: fail honestly instead of scaffolding
        # part of it and reporting success for a workspace that is still broken.
        names = ", ".join(f"`{m}`" for m in blocked)
        print(f"Cannot initialize workspace: {names} exists as a file, not a directory. "
              f"Remove it, then run `hlab init` again.", file=sys.stderr)
        return 1
    result = scaffold.init_workspace(root)
    print(f"Initialized Agent Harness Lab workspace: {root}")
    if result.created:
        for c in result.created:
            print(f"  + {c}")
    else:
        print("  (nothing to create — workspace already initialized)")
    print()
    print("Next:")
    print("  1. Edit goal.md — what behavior of which agent are you improving?")
    print("  2. hlab new <experiment-name>   (--mode copilot|auto, --execution ab|sequential|longitudinal|replay)")
    print("  3. hlab review experiments/<name>")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    root = Path.cwd()
    exps = root / "experiments"
    if not exps.exists():
        print("No experiments/ directory — run `hlab init` first.", file=sys.stderr)
        return 1
    if not exps.is_dir():
        print("`experiments` exists but is not a directory — workspace is broken; "
              "remove it and run `hlab init`.", file=sys.stderr)
        return 1
    try:
        result = scaffold.new_experiment(
            root, args.name, run_mode=args.mode, execution_mode=args.execution)
    except (ValueError, FileExistsError) as e:
        print(str(e), file=sys.stderr)
        return 1
    eid = result.experiment_id
    note = f"  (name normalized to id '{eid}')" if eid != args.name else ""
    print(f"Created experiment: experiments/{eid}  "
          f"(run.mode={args.mode}, execution.mode={args.execution}){note}")
    print(f"  {result.experiment_dir}")
    print("    experiment.md        — human plan")
    print("    experiment.yaml      — machine source of truth")
    print("    harnesses/A, B/      — compared harnesses")
    _conn = "manual" if args.mode == "copilot" else "local_cli"
    print(f"    agent-runtimes/      — Agent Runtime specs ({_conn})")
    print("    cases/cases.jsonl    — executable inputs")
    print("    evaluation/          — evaluators + tracks (workspace methods in ../../evaluation-methods/)")
    print("    evidence/            — run evidence store")
    print("    reports/             — generated reports")
    print("    conclusion.md        — human conclusion")
    print()
    print(f"Next: edit the templates, then `hlab review experiments/{eid}`")
    return 0


def _print_review(report) -> None:
    for p in report.errors:
        print(f"  ERROR  {p.code}: {p.message}")
    for p in report.warnings:
        print(f"  WARN   {p.code}: {p.message}")


def cmd_review(args: argparse.Namespace) -> int:
    exp_dir = _resolve_experiment(args.experiment)
    if exp_dir is None:
        print(f"Experiment not found: {args.experiment}", file=sys.stderr)
        return 1
    report = review_experiment(exp_dir)
    print(f"review: {exp_dir}")
    print(f"verdict: {report.verdict}")
    _print_review(report)
    if report.verdict == PASS:
        print("  OK — no problems found.")
        return 0
    if report.verdict == WARN:
        print(f"  {len(report.warnings)} warning(s); experiment may still run.")
        return 0
    # ERROR
    print(f"  {len(report.errors)} error(s) must be fixed before running.")
    return 1


def cmd_run(args: argparse.Namespace) -> int:
    exp_dir = _resolve_experiment(args.experiment)
    if exp_dir is None:
        print(f"Experiment not found: {args.experiment}", file=sys.stderr)
        return 1
    report = review_experiment(exp_dir)
    if report.verdict == ERROR:
        # Refuse to generate a misleading task from a broken experiment.
        print(f"run blocked: experiment.yaml has {len(report.errors)} error(s) — "
              f"fix them first (`hlab review {args.experiment}`). Nothing was generated.",
              file=sys.stderr)
        _print_review(report)
        return 1
    try:
        spec = parse_experiment_yaml(exp_dir / "experiment.yaml")
    except ExperimentSpecError as e:
        print(str(e), file=sys.stderr)
        return 1

    if spec.run_mode == "copilot":
        # Copilot Mode: AHL prepares the task; an external agent executes it.
        if report.verdict == WARN:
            _print_review(report)  # non-blocking, but surface for transparency
        target = copilot.write_agent_task(exp_dir, spec)
        rel = str(target)  # OS-normalized path (no mixed separators)
        print(f"Copilot Mode (run.mode=copilot, execution.mode={spec.execution_mode}):")
        print(f"  - agent-task.md was generated: {rel}")
        print("    (rendered from experiment.yaml + experiment.md; not the source of truth)")
        print("  - no Agent Runtime was directly executed")
        print("  - no evidence was collected yet")
        print(f"Next: hand {copilot.AGENT_TASK_FILENAME} to your execution agent "
              f"(Claude Code / Codex / Cursor Agent), then `hlab status {args.experiment}`.")
        return 0

    if spec.run_mode == "auto":
        # Auto Mode: AHL drives the runtimes via connectors and collects evidence.
        if report.verdict == WARN:
            _print_review(report)  # non-blocking, but surface for transparency
        from agent_harness_lab import auto
        res = auto.run_auto(exp_dir, spec)
        print(f"Auto Mode (run.mode=auto, execution.mode={spec.execution_mode}):")
        print(f"  - dispatched {res.dispatched} case run(s) "
              f"({res.cases} case(s) × {res.runtimes} runtime(s))")
        print(f"  - evidence written under: {res.evidence_dir}")
        print(f"  - traces: {res.traces_written}  |  issues: {len(res.issues)}", end="")
        counts = res.issue_counts()
        print(f"  {counts}" if counts else "")
        print("  - no report was generated (ReportBuilder is a later phase)")
        return 0

    # Any other run.mode is not executable in v1.
    print(f"run: {exp_dir}  (run.mode={spec.run_mode}, execution.mode={spec.execution_mode})",
          file=sys.stderr)
    print(f"NOT IMPLEMENTED: run.mode={spec.run_mode!r} is not executable "
          f"(use copilot or auto).", file=sys.stderr)
    return 2


def cmd_status(args: argparse.Namespace) -> int:
    exp_dir = _resolve_experiment(args.experiment)
    if exp_dir is None:
        print(f"Experiment not found: {args.experiment}", file=sys.stderr)
        return 1
    yaml_path = exp_dir / "experiment.yaml"
    if not yaml_path.exists():
        print(f"No experiment.yaml in {exp_dir}", file=sys.stderr)
        return 1
    try:
        spec = parse_experiment_yaml(yaml_path)
    except ExperimentSpecError as e:
        print(str(e), file=sys.stderr)
        return 1

    case_count = 0
    if spec.cases_root and spec.cases_files:
        try:
            case_count = len(load_cases(exp_dir / spec.cases_root, spec.cases_files))
        except ExperimentSpecError:
            case_count = -1  # unreadable

    evidence_dir = exp_dir / "evidence"
    issues_path = evidence_dir / "issues.jsonl"
    issue_count = 0
    if issues_path.exists():
        issue_count = sum(1 for ln in issues_path.read_text(encoding="utf-8").splitlines() if ln.strip())
    evidence_has = []
    if evidence_dir.exists():
        for sub in ("traces", "raw", "artifacts", "snapshots", "scores", "inspections"):
            d = evidence_dir / sub
            # ignore the scaffold .gitkeep marker — it is not collected evidence
            if d.is_dir() and any(f.name != ".gitkeep" for f in d.iterdir()):
                evidence_has.append(sub)
    report_md = (exp_dir / "reports" / "report.md").exists()
    conclusion = (exp_dir / "conclusion.md").exists()

    # reflect harness names, runtime->harness mapping + connector type
    harness_str = ", ".join(f"{h.id}={h.name}" for h in spec.harnesses if h.id) or "(none)"
    rt_bits = []
    for r in spec.agent_runtimes:
        ctype = "?"
        if isinstance(r.spec, str) and r.spec:
            sp = exp_dir / r.spec
            if not sp.exists():
                ctype = "(missing spec)"
            else:
                try:
                    ctype = load_agent_runtime_spec(sp).connector_type or "?"
                except ExperimentSpecError:
                    ctype = "(unreadable)"
        rt_bits.append(f"{r.id}→{r.harness} ({ctype})")
    rt_str = ", ".join(rt_bits) or "(none)"

    # reflect collection / inspection config (so the values are visibly read)
    coll = spec.collection if isinstance(spec.collection, dict) else {}
    on = [k for k in _COLLECTION_KEYS if coll.get(k)]
    off = [k for k in _COLLECTION_KEYS if k in coll and not coll.get(k)]
    coll_str = ("on: " + ", ".join(on) if on else "on: (none)")
    if off:
        coll_str += " | off: " + ", ".join(off)
    insp = spec.inspection if isinstance(spec.inspection, dict) else {}
    reviews = [k for k in _REVIEW_KEYS if insp.get(k)]
    checks = insp.get("issue_checks") or []
    insp_str = ("reviews: " + ", ".join(reviews) if reviews else "reviews: (none)")
    insp_str += " | checks: " + (", ".join(checks) if checks else "(none)")

    print(f"experiment id:   {spec.id or '(unset)'}")
    print(f"status:          {spec.status or '(unset)'}")
    print(f"question:        {spec.question or '(unset)'}")
    print(f"run mode:        {spec.run_mode or '(unset)'}")
    print(f"execution mode:  {spec.execution_mode or '(unset)'}  "
          f"(state_policy={spec.state_policy or '(unset)'})")
    print(f"harness count:   {len(spec.harnesses)}")
    print(f"  harnesses:     {harness_str}")
    print(f"agent runtimes:  {rt_str}")
    print(f"case count:      {case_count if case_count >= 0 else '(unreadable)'}")
    print(f"collection:      {coll_str}")
    print(f"inspection:      {insp_str}")
    print(f"evidence:        {', '.join(evidence_has) if evidence_has else 'none collected'}")
    print(f"issues:          {issue_count}")
    print(f"report:          {'reports/report.md present' if report_md else 'none'}")
    print(f"conclusion:      {'present' if conclusion else 'missing'}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    exp_dir = _resolve_experiment(args.experiment)
    if exp_dir is None:
        print(f"Experiment not found: {args.experiment}", file=sys.stderr)
        return 1
    # Symmetric with `run`: a broken experiment.yaml is a real error (exit 1),
    # not "not implemented".
    report = review_experiment(exp_dir)
    if report.verdict == ERROR:
        print(f"report blocked: experiment.yaml has {len(report.errors)} error(s) — "
              f"fix them first (`hlab review {args.experiment}`).", file=sys.stderr)
        _print_review(report)
        return 1
    # Phase 1 does not generate reports. Exit 2 = not implemented in this phase.
    print(f"report: {exp_dir}", file=sys.stderr)
    print("NOT IMPLEMENTED in this phase:", file=sys.stderr)
    print("  - no report was generated", file=sys.stderr)
    print("  (ReportBuilder — reports/report.md and reports/report.html — "
          "lands in a later phase.)", file=sys.stderr)
    return 2


# --- parser / entry ----------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hlab",
        description="Agent Harness Lab: run goal-driven harness experiments on "
                    "real Agent Runtimes.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_init = sub.add_parser("init", help="initialize a workspace (goal.md, evaluation-methods/, experiments/, .hlab/)")
    p_init.set_defaults(func=cmd_init)

    p_new = sub.add_parser("new", help="create an experiment", allow_abbrev=False)
    p_new.add_argument("name", help="experiment name -> experiments/<name>/")
    p_new.add_argument("--mode", choices=["copilot", "auto"], default="copilot",
                       help="run mode (default: copilot)")
    p_new.add_argument("--execution", choices=["ab", "sequential", "longitudinal", "replay"],
                       default="ab", help="execution mode (default: ab)")
    p_new.set_defaults(func=cmd_new)

    p_review = sub.add_parser("review", help="review an experiment before run (PASS/WARN/ERROR)")
    p_review.add_argument("experiment", help="experiments/<name> or <name>")
    p_review.set_defaults(func=cmd_review)

    p_run = sub.add_parser("run", help="run or prepare an experiment (per run.mode)")
    p_run.add_argument("experiment", help="experiments/<name> or <name>")
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="show experiment status and evidence state")
    p_status.add_argument("experiment", help="experiments/<name> or <name>")
    p_status.set_defaults(func=cmd_status)

    p_report = sub.add_parser("report", help="generate or refresh reports")
    p_report.add_argument("experiment", help="experiments/<name> or <name>")
    p_report.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except Exception as e:  # safety net: never surface a raw traceback to the user
        print(f"internal error ({type(e).__name__}): {e}", file=sys.stderr)
        print("This is a bug — please report it. The experiment was not modified.",
              file=sys.stderr)
        return 1


def ahl_redirect(argv: list[str] | None = None) -> int:
    """Entry point for the retired `ahl` command — friendly migration message.

    Does not run old semantics (meaning changed in v1)."""
    _utf8_streams()
    rest = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "<command>"
    print("The `ahl` command has been replaced by `hlab` (Agent Harness Lab v1).",
          file=sys.stderr)
    print(f"Please use: hlab {rest}", file=sys.stderr)
    print("Run `hlab --help` for the v1 command surface "
          "(init / new / review / run / status / report).", file=sys.stderr)
    return 1
