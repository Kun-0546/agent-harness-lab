"""Agent Harness Lab — `hlab` command-line entry (v1).

Eight public commands: init / new / review / run / status / report / compare /
conclude. This layer parses args, prints results, and delegates to the copilot /
scaffold / reviewer / experiment_spec / auto / evaluation / report / compare /
conclude modules.

What the commands cover in v1:
- Copilot Mode — `run` renders an agent-task.md for an external agent to execute.
- Auto Run — `run` drives the configured Agent Runtimes, then collects, inspects,
  and evaluates the resulting evidence.
- Auto Optimize — a bounded, deterministic (copy-only / script-based)
  candidate -> evaluate -> promote loop; it is not LLM-driven or autonomous.
- evidence / evaluation / report — `status` shows evidence and evaluation state;
  `report` builds reports/report.md from the collected evidence.

Exit codes (v1 contract): 0 success / 1 configuration or preflight error /
2 not implemented / 3 runtime failure (any error-severity issue, or any
evaluation track whose status is `error`). Pending evaluations (no judge key /
no annotation yet), failed evaluations ("the answer is a failure" is a
legitimate result) and warn/info-level issues do NOT fail the run.

Runs on Python 3.10-3.12. Modules in the package that are not reached by this CLI
surface are internal and not part of the public API.
"""
from __future__ import annotations

import argparse
import json
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
    template = getattr(args, "template", None)
    question = getattr(args, "question", None)
    try:
        result = scaffold.new_experiment(
            root, args.name, run_mode=args.mode, execution_mode=args.execution,
            question=question, template=template)
    except KeyError:
        print(f"Unknown template: {template!r}. Available templates: "
              f"{', '.join(sorted(scaffold.TEMPLATES)) or '(none)'}", file=sys.stderr)
        return 1
    except (ValueError, FileExistsError) as e:
        print(str(e), file=sys.stderr)
        return 1
    eid = result.experiment_id
    note = f"  (name normalized to id '{eid}')" if eid != args.name else ""
    if template:
        print(f"Created experiment from template '{template}': experiments/{eid}{note}")
        if question:
            print("  (--question is ignored with --template: the template defines "
                  "its own question)")
        print(f"  {result.experiment_dir}")
        print("  A complete, runnable A/B experiment was generated "
              "(harnesses, runtimes, cases, and a deterministic benchmark).")
        print()
        print(f"Next: hlab review  experiments/{eid}")
        print(f"      hlab run     experiments/{eid}")
        print(f"      hlab report  experiments/{eid}")
        print(f"      hlab compare experiments/{eid}")
        print(f"      hlab conclude experiments/{eid} --winner <id> --reason \"...\"")
        return 0
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
    q_hint = "" if question else " — fill `question:` in experiment.yaml (or pass --question)"
    print(f"Next: edit the templates{q_hint}, then:")
    print(f"      hlab review experiments/{eid}")
    print(f"      hlab run    experiments/{eid}")
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
        print(f"Next: hlab run {args.experiment}")
        return 0
    if report.verdict == WARN:
        print(f"  {len(report.warnings)} warning(s); experiment may still run.")
        print(f"Next: address the warning(s), or proceed with `hlab run {args.experiment}`.")
        return 0
    # ERROR
    print(f"  {len(report.errors)} error(s) must be fixed before running.")
    print(f"Next: fix the error(s), then run `hlab review {args.experiment}` again.")
    return 1


# --- run-failure judgement (the exit-code contract) ---------------------------

def _runtime_failure_exit(issues: list[dict], track_statuses: list[tuple[str, str]],
                          *, evidence_ref: str = "evidence/") -> int:
    """The unified exit-3 judgement: 3 on any severity==error issue
    (HLAB_RUNTIME_FAILURE) or any evaluation track with status==error
    (HLAB_EVAL_ERROR); else 0. Exempt by contract: pending tracks (no judge key /
    no annotation yet), failed tracks (a failed experiment answer is a legitimate
    result), and warn/info-level issues. On failure, machine-readable HLAB_*
    error codes go to stderr (the exit code routes a loop gate; the code names
    the branch for an agent)."""
    error_issues = [i for i in issues if isinstance(i, dict) and i.get("severity") == "error"]
    error_tracks = [tid for tid, status in track_statuses if status == "error"]
    if not error_issues and not error_tracks:
        return 0
    if error_issues:
        counts: dict[str, int] = {}
        for i in error_issues:
            t = str(i.get("type") or "unknown")
            counts[t] = counts.get(t, 0) + 1
        detail = ", ".join(f"{t}={n}" for t, n in sorted(counts.items()))
        print(f"HLAB_RUNTIME_FAILURE: {len(error_issues)} error-severity issue(s) "
              f"({detail}) — see {evidence_ref}issues.jsonl", file=sys.stderr)
    if error_tracks:
        print(f"HLAB_EVAL_ERROR: {len(error_tracks)} evaluation track(s) errored "
              f"({', '.join(sorted(error_tracks))}) — see {evidence_ref}scores/tracks/",
              file=sys.stderr)
    return 3


def _track_statuses(evidence_dir: Path) -> list[tuple[str, str]]:
    """[(track_id, status)] from an evidence dir's aggregated track files."""
    out: list[tuple[str, str]] = []
    tracks_dir = evidence_dir / "scores" / "tracks"
    if not tracks_dir.is_dir():
        return out
    for p in sorted(tracks_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append((str(d.get("track_id") or p.stem), str(d.get("status") or "")))
    return out


def _optimize_final_evidence_dir(exp_dir: Path, opt_res) -> Path | None:
    """The evidence dir that represents the FINAL incumbent — the Auto Optimize
    exit judges that, never the union of all iterations. It is the last PROMOTED
    iteration's evidence (that candidate is the incumbent now); with zero
    promotions the incumbent never changed, so fall back to the last iteration
    that actually ran (mutation-rejected iterations leave no evidence). None if
    no iteration ran at all."""
    promoted = last = None
    for ir in opt_res.iterations:
        ev = exp_dir / "optimization" / "iterations" / f"iter-{ir.iteration:03d}" / "evidence"
        if not ev.is_dir():
            continue
        last = ev
        if ir.promoted:
            promoted = ev
    return promoted if promoted is not None else last


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
        from agent_harness_lab import auto, evaluation, inspector
        # Auto Mode = Auto Run + Auto Optimize. If optimization is enabled, run the
        # bounded candidate→evaluate→promote loop (each iteration is an Auto Run).
        if spec.optimization and spec.optimization.enabled:
            from agent_harness_lab import auto_optimize
            opt_res = auto_optimize.run_optimization(exp_dir, spec)
            print("Auto Optimize (run.mode=auto, optimization.enabled):")
            print(f"  - {len(opt_res.iterations)} iteration(s), {opt_res.promotions} promotion(s); "
                  f"stopped by {opt_res.stopped_by}")
            print(f"  - incumbent harness: {opt_res.incumbent_dir}")
            print(f"  - history: {exp_dir / 'optimization' / 'history.jsonl'}")
            print(f"Next: hlab report {args.experiment}")
            final_ev = _optimize_final_evidence_dir(exp_dir, opt_res)
            if final_ev is None:
                return 0  # no iteration ran (e.g. every mutation was rejected)
            return _runtime_failure_exit(
                inspector._read_issues(final_ev / "issues.jsonl"),
                _track_statuses(final_ev),
                evidence_ref=f"optimization/iterations/{final_ev.parent.name}/evidence/")
        res = auto.run_auto(exp_dir, spec)
        print(f"Auto Mode (run.mode=auto, execution.mode={spec.execution_mode}):")
        print(f"  - dispatched {res.dispatched} case run(s) "
              f"({res.cases} case(s) × {res.runtimes} runtime(s))")
        print(f"  - evidence written under: {res.evidence_dir}")
        print(f"  - traces: {res.traces_written}  |  issues: {len(res.issues)}", end="")
        counts = res.issue_counts()
        print(f"  {counts}" if counts else "")
        # Evaluation: run each track's evaluators over the evidence just collected.
        ev_result = (evaluation.run_evaluation(exp_dir, spec)
                     if spec.evaluators else evaluation.EvaluationResult())
        if ev_result.ran:
            from agent_harness_lab import report_builder
            comp = report_builder.comparative_summary(exp_dir, spec)
            if comp:
                # multi-harness A/B: a comparison with a winner, not a "failed" track
                display: dict[str, int] = {}
                for t in ev_result.tracks:
                    st = "comparative" if t.track_id == comp["primary"] else t.status
                    display[st] = display.get(st, 0) + 1
                print(f"  - evaluation: {len(ev_result.tracks)} track(s) {display}")
                if comp["winner"]:
                    met = "objective met" if comp["objective_met"] else "objective not met"
                    print(f"    objective primary track '{comp['primary']}': comparative — "
                          f"winner {comp['winner']} ({comp['winner_name']}), {met}")
                else:
                    print(f"    objective primary track '{comp['primary']}': comparative — "
                          f"no single winner")
            else:
                print(f"  - evaluation: {len(ev_result.tracks)} track(s) {ev_result.status_counts()}")
                if ev_result.objective_track:
                    print(f"    objective primary track '{ev_result.objective_track}': "
                          f"{ev_result.objective_status}")
        else:
            print("  - evaluation: no tracks configured (nothing evaluated)")
        # Inspection: completeness checks over the evidence + scores (merges issues).
        insp = inspector.run_inspection(exp_dir, spec)
        print(f"  - inspection: +{len(insp.added)} issue(s) → {insp.issue_total} total "
              f"{insp.severity_counts()}")
        print(f"Next: hlab report {args.experiment}")
        # exit-code contract: judge the merged issue set + the evaluated tracks
        return _runtime_failure_exit(
            insp.issues, [(t.track_id, t.status) for t in ev_result.tracks])

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
    # evaluation: reflect aggregated per-track statuses written by EvaluationRunner
    tracks_dir = evidence_dir / "scores" / "tracks"
    from agent_harness_lab import report_builder
    _comp = report_builder.comparative_summary(exp_dir, spec)
    eval_bits = []
    if tracks_dir.is_dir():
        for p in sorted(tracks_dir.glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            tid = d.get("track_id")
            if _comp and tid == _comp["primary"]:
                w = f" (winner {_comp['winner']})" if _comp.get("winner") else ""
                eval_bits.append(f"{tid}=comparative{w}")
            else:
                eval_bits.append(f"{tid}={d.get('status')}")
    print(f"evaluation:      {', '.join(eval_bits) if eval_bits else 'none run'}")
    print(f"issues:          {issue_count}")
    print(f"report:          {'reports/report.md present' if report_md else 'none'}")
    print(f"conclusion:      {'present' if conclusion else 'missing'}")
    if not evidence_has:
        print(f"Next: hlab run {args.experiment}")
    elif not report_md:
        print(f"Next: hlab report {args.experiment}")
    else:
        print(f"Next: hlab compare {args.experiment}, then `hlab conclude "
              f"{args.experiment} --winner <id> --reason \"...\"`.")
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
    try:
        spec = parse_experiment_yaml(exp_dir / "experiment.yaml")
    except ExperimentSpecError as e:
        print(str(e), file=sys.stderr)
        return 1
    if report.verdict == WARN:
        _print_review(report)  # non-blocking, but surface for transparency
    from agent_harness_lab import report_builder
    md_path = report_builder.build_report(exp_dir, spec)
    print(f"report generated: {md_path}")
    print("  - summarizes harnesses, runtimes, evidence, issues, evaluation tracks, "
          "objective, and Auto Optimize state")
    print("  - pending llm_judge/human evaluations and an unrun Auto Optimize loop are "
          "marked honestly; no conclusion is fabricated")
    print(f"Next: hlab compare {args.experiment}, then record your decision with "
          f"`hlab conclude {args.experiment} --winner <id> --reason \"...\"`.")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    exp_dir = _resolve_experiment(args.experiment)
    if exp_dir is None:
        print(f"Experiment not found: {args.experiment}", file=sys.stderr)
        return 1
    report = review_experiment(exp_dir)
    if report.verdict == ERROR:
        print(f"compare blocked: experiment.yaml has {len(report.errors)} error(s) — "
              f"fix them first (`hlab review {args.experiment}`).", file=sys.stderr)
        _print_review(report)
        return 1
    try:
        spec = parse_experiment_yaml(exp_dir / "experiment.yaml")
    except ExperimentSpecError as e:
        print(str(e), file=sys.stderr)
        return 1
    from agent_harness_lab import compare
    out_path, data = compare.write_comparison(exp_dir, spec)
    print(compare.format_summary(data))
    print()
    print(f"compare written: {out_path}")
    print(f"Next: record your decision with `hlab conclude {args.experiment} "
          f"--winner {data['winner'] or '<id>'} --reason \"...\"`.")
    return 0


def cmd_conclude(args: argparse.Namespace) -> int:
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
    from agent_harness_lab import conclude
    out = conclude.write_conclusion(exp_dir, spec, winner=args.winner, reason=args.reason)
    print(f"conclusion recorded: {out}")
    if args.winner:
        print(f"  - winner: {args.winner}")
    print("  - this is your decision, not a generated verdict")
    print(f"  - `hlab review {args.experiment}` will no longer warn conclusion_missing")
    print("Next: the experiment loop is complete — start the next one with `hlab new <name>`.")
    return 0


# --- parser / entry ----------------------------------------------------------

# The object model in one sentence, then the loop stages — the top-level help is
# the first contact with the tool, so it must teach the model, not list verbs.
_CLI_DESCRIPTION = """\
Agent Harness Lab: run goal-driven harness experiments on real Agent Runtimes.

hlab has exactly two objects: the WORKSPACE and the EXPERIMENT. `hlab init`
creates the workspace; every other command acts on one experiment directory
(experiments/<name> — addressable as a path or a bare name).
"""

_CLI_EPILOG = """\
the experiment loop (commands by stage):
  prepare           init, new
  gate & execute    review, run, status
  conclude          report, compare, conclude

exit codes:
  0  success
  1  configuration / preflight error
  2  not implemented in v1
  3  runtime failure (an error-severity issue, or an evaluation track in `error`)
"""

_EXPERIMENT_ARG_HELP = "experiments/<name>, a path, or the bare experiment name"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hlab",
        description=_CLI_DESCRIPTION,
        epilog=_CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # prepare ------------------------------------------------------------------
    p_init = sub.add_parser(
        "init",
        help="create the workspace in the current directory "
             "(goal.md, evaluation-methods/, experiments/, .hlab/)")
    p_init.set_defaults(func=cmd_init)

    p_new = sub.add_parser(
        "new", allow_abbrev=False,
        help="<name>: create the experiment experiments/<name>/ "
             "(--mode, --execution, --question, --template)")
    p_new.add_argument("name", metavar="<name>", help="experiment name -> experiments/<name>/")
    p_new.add_argument("--mode", choices=["copilot", "auto"], default="copilot",
                       help="run mode (default: copilot)")
    p_new.add_argument("--execution", choices=["ab", "sequential", "longitudinal", "replay"],
                       default="ab", help="execution mode (default: ab)")
    p_new.add_argument("--question", metavar="TEXT",
                       help="the one-line experiment question, written into experiment.yaml "
                            "(otherwise a <placeholder> is scaffolded and `hlab review` warns)")
    p_new.add_argument("--template", metavar="NAME",
                       help="scaffold a complete, runnable experiment from a built-in "
                            "template (e.g. memory-policy-ab-lite)")
    p_new.set_defaults(func=cmd_new)

    # gate & execute -----------------------------------------------------------
    p_review = sub.add_parser(
        "review", help="<experiment>: gate it before run — PASS / WARN / ERROR")
    p_review.add_argument("experiment", metavar="<experiment>", help=_EXPERIMENT_ARG_HELP)
    p_review.set_defaults(func=cmd_review)

    p_run = sub.add_parser(
        "run", help="<experiment>: execute it (Auto Mode) or render its "
                    "agent-task.md (Copilot Mode)")
    p_run.add_argument("experiment", metavar="<experiment>", help=_EXPERIMENT_ARG_HELP)
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser(
        "status", help="<experiment>: show its spec, evidence, and evaluation state")
    p_status.add_argument("experiment", metavar="<experiment>", help=_EXPERIMENT_ARG_HELP)
    p_status.set_defaults(func=cmd_status)

    # conclude -----------------------------------------------------------------
    p_report = sub.add_parser(
        "report", help="<experiment>: build reports/report.md (+ .html) from its evidence")
    p_report.add_argument("experiment", metavar="<experiment>", help=_EXPERIMENT_ARG_HELP)
    p_report.set_defaults(func=cmd_report)

    p_compare = sub.add_parser(
        "compare", help="<experiment>: summarize its A/B result into reports/compare.json")
    p_compare.add_argument("experiment", metavar="<experiment>", help=_EXPERIMENT_ARG_HELP)
    p_compare.set_defaults(func=cmd_compare)

    p_conclude = sub.add_parser(
        "conclude", help="<experiment>: record YOUR decision as conclusion.md "
                         "(--winner, --reason)")
    p_conclude.add_argument("experiment", metavar="<experiment>", help=_EXPERIMENT_ARG_HELP)
    p_conclude.add_argument("--winner", metavar="ID", help="the harness id you chose (e.g. B)")
    p_conclude.add_argument("--reason", help="one-line reason for the decision")
    p_conclude.set_defaults(func=cmd_conclude)

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
    """Entry point for the retired `ahl` command — an honest stop, not a shim.

    Does not run old semantics (meaning changed in v1), and does not pretend the
    old arguments map onto `hlab` — the two stacks are not compatible."""
    _utf8_streams()
    print("`ahl` (the v0.x stack) is retired and no longer runs.", file=sys.stderr)
    print("Its successor is `hlab` (Agent Harness Lab v1), but the two stacks' "
          "workspace formats are NOT compatible:", file=sys.stderr)
    print("an `ahl` workspace cannot be opened by `hlab`, and old `ahl` commands "
          "do not map 1:1 onto the v1 surface.", file=sys.stderr)
    print("Start fresh with `hlab init` + `hlab --help`; see the README's "
          "'Command surface' section for the v1 loop. A migration guide "
          "(migrating-from-ahl.md) is planned for v1.1.", file=sys.stderr)
    return 1
