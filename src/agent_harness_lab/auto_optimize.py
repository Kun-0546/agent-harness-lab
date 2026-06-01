"""Auto Optimize — a bounded, deterministic candidate→evaluate→promote loop.

This is NOT a general autonomous agent. Candidate harnesses are generated
deterministically (copy-only, or via a user `mutation_script`); there is NO
LLM-driven mutation. Roles are Candidate Harness / Incumbent Harness (never the
public word "variant").

Per iteration:
  1. copy the incumbent harness → harnesses/candidates/iter-NNN/
  2. if optimization.mutation_script is set, run it to mutate the candidate
     (args: incumbent_dir candidate_dir iteration objective_context.json)
  3. enforce the protected surface (goal / cases / evaluation / objective /
     conclusion) is unchanged — a candidate may only edit the editable surface
  4. Auto Run the candidate (working_dir = candidate dir) into a per-iteration
     evidence dir, then Inspector, then EvaluationRunner
  5. compare to the incumbent via promotion_policy → promote (candidate becomes the
     new incumbent) or reject
  6. append optimization/history.jsonl + optimization/iterations/iter-NNN.json
  7. stop on stop_conditions (max_iterations / no_improvement)

A safety cap bounds iterations even if stop_conditions is missing a max.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from agent_harness_lab.agentconn import _POSIX, _pgid_of
from agent_harness_lab.auto import _read_text, _sweep_group, run_auto
from agent_harness_lab.evaluation import run_evaluation
from agent_harness_lab.experiment_spec import ExperimentSpec
from agent_harness_lab.inspector import run_inspection

_SAFETY_CAP = 10  # never loop forever even if stop_conditions omits a max

try:
    _MUT_TIMEOUT = float(os.environ.get("AHL_OPTIMIZE_TIMEOUT", "60"))
except ValueError:
    _MUT_TIMEOUT = 60.0


@dataclass
class IterationResult:
    iteration: int
    candidate_dir: str
    primary_status: str | None = None
    score: float | None = None
    issues: int = 0
    promoted: bool = False
    reason: str = ""


@dataclass
class OptimizeResult:
    iterations: list[IterationResult] = field(default_factory=list)
    incumbent_dir: str | None = None
    promotions: int = 0
    stopped_by: str = "max_iterations"
    note: str = ""

    @property
    def ran(self) -> bool:
        return bool(self.iterations) or bool(self.note)


def _parse_stops(opt) -> tuple[int, int | None]:
    max_iter: int | None = None
    patience: int | None = None
    for sc in opt.stop_conditions or []:
        if not isinstance(sc, dict):
            continue
        t = sc.get("type")
        if t == "max_iterations":
            max_iter = sc.get("value", sc.get("max"))
        elif t == "no_improvement":
            patience = sc.get("patience", sc.get("value"))
        else:  # single-key form: {max_iterations: N} / {no_improvement: K}
            if "max_iterations" in sc:
                max_iter = sc["max_iterations"]
            if "no_improvement" in sc:
                patience = sc["no_improvement"]
    max_iter = int(max_iter) if isinstance(max_iter, (int, float)) and max_iter > 0 else _SAFETY_CAP
    max_iter = min(max_iter, _SAFETY_CAP)
    patience = int(patience) if isinstance(patience, (int, float)) and patience > 0 else None
    return max_iter, patience


def _parse_promotion(opt) -> tuple[bool, bool, object]:
    pp = opt.promotion_policy or {}
    require_primary = pp.get("require_primary_track_passed", True) is not False
    allow_pending = bool(pp.get("allow_pending", False))
    block_on_issues = pp.get("block_on_issues", True)
    return require_primary, allow_pending, block_on_issues


def _protected_files(exp_dir: Path, spec: ExperimentSpec) -> list[Path]:
    """The protected surface: goal / cases / evaluation / objective / conclusion +
    experiment.yaml. A candidate may only edit the editable (harness) surface."""
    paths: list[Path] = [exp_dir / "experiment.yaml", exp_dir / "conclusion.md",
                         exp_dir / "goal.md"]
    if isinstance(spec.goal_ref, str) and spec.goal_ref:
        paths.append(exp_dir / spec.goal_ref)
    for sub in ("cases", "evaluation"):
        d = exp_dir / sub
        if d.is_dir():
            paths.extend(p for p in d.rglob("*") if p.is_file())
    return paths


def _protected_capture(exp_dir: Path, spec: ExperimentSpec) -> dict[str, bytes]:
    cap: dict[str, bytes] = {}
    for p in _protected_files(exp_dir, spec):
        try:
            if p.is_file():
                cap[str(p)] = p.read_bytes()
        except OSError:
            continue
    return cap


def _restore_protected(before: dict[str, bytes], after: dict[str, bytes]) -> None:
    """Roll the protected surface back to `before`: rewrite changed files and delete
    any file a mutation newly created. The candidate's edits to its own (editable)
    harness dir are untouched."""
    for k, v in before.items():
        try:
            Path(k).write_bytes(v)
        except OSError:
            pass
    for k in set(after) - set(before):
        try:
            Path(k).unlink()
        except OSError:
            pass


def _run_mutation(script: Path, incumbent: Path, candidate: Path, iteration: int,
                  ctx: Path, exp_dir: Path, iterdir: Path) -> int | None:
    """Run the mutation script bounded (file-redirected + proc.wait + group sweep).
    Returns the exit code, or None on timeout."""
    so, se = iterdir / "mutation.stdout.txt", iterdir / "mutation.stderr.txt"
    with open(so, "w", encoding="utf-8") as fo, open(se, "w", encoding="utf-8") as fe:
        proc = subprocess.Popen(
            [sys.executable, str(script), str(incumbent), str(candidate),
             str(iteration), str(ctx)],
            shell=False, cwd=str(exp_dir),
            stdin=subprocess.DEVNULL, stdout=fo, stderr=fe,
            text=True, encoding="utf-8", close_fds=True, start_new_session=_POSIX,
        )
        pgid = _pgid_of(proc)
        try:
            proc.wait(timeout=_MUT_TIMEOUT)
        except subprocess.TimeoutExpired:
            _sweep_group(proc, pgid)
            return None
    _sweep_group(proc, pgid)
    return proc.returncode


def _primary_score(ev_result, primary_track) -> float | None:
    for t in ev_result.tracks:
        if t.track_id == primary_track:
            scores = [o.score for o in t.evaluators if isinstance(o.score, (int, float))]
            return sum(scores) / len(scores) if scores else None
    return None


def _count_blocking(evidence_dir: Path, block_on_issues) -> int:
    p = evidence_dir / "issues.jsonl"
    if not p.is_file() or block_on_issues is False:
        return 0
    issues = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                issues.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    if isinstance(block_on_issues, list):
        return sum(1 for i in issues if i.get("type") in block_on_issues)
    return sum(1 for i in issues if i.get("severity") == "error")  # block_on_issues truthy


def run_optimization(exp_dir: Path, spec: ExperimentSpec) -> OptimizeResult:
    """Run the bounded Auto Optimize loop. Requires spec.optimization.enabled."""
    exp_dir = Path(exp_dir).resolve()
    result = OptimizeResult()
    opt = spec.optimization
    if opt is None or not opt.enabled:
        result.note = "optimization not enabled"
        return result

    max_iter, patience = _parse_stops(opt)
    require_primary, allow_pending, block_on_issues = _parse_promotion(opt)
    primary_track = spec.objective.primary_track if spec.objective else None

    harnesses = exp_dir / "harnesses"
    incumbent = harnesses / "incumbent"
    if not incumbent.exists():
        base = (exp_dir / spec.harnesses[0].path) if spec.harnesses else None
        if base and base.is_dir():
            shutil.copytree(base, incumbent)
        else:
            incumbent.mkdir(parents=True, exist_ok=True)

    mutation_script = None
    _ms = opt.raw.get("mutation_script") if isinstance(opt.raw, dict) else None
    if isinstance(_ms, str) and _ms:
        cand_script = (exp_dir / _ms).resolve()
        if cand_script.is_file():
            mutation_script = cand_script

    opt_dir = exp_dir / "optimization"
    iters_dir = opt_dir / "iterations"
    iters_dir.mkdir(parents=True, exist_ok=True)
    history: list[dict] = []

    best_score: float | None = None
    incumbent_passed = False
    no_improve = 0

    for n in range(1, max_iter + 1):
        iterdir = iters_dir / f"iter-{n:03d}"
        iterdir.mkdir(parents=True, exist_ok=True)
        candidate = harnesses / "candidates" / f"iter-{n:03d}"
        if candidate.exists():
            shutil.rmtree(candidate, ignore_errors=True)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(incumbent, candidate)

        ir = IterationResult(iteration=n, candidate_dir=str(candidate))

        if mutation_script is not None:
            ctx = iterdir / "objective.json"
            ctx.write_text(json.dumps({
                "iteration": n, "objective": (spec.objective.raw if spec.objective else None),
                "incumbent_dir": str(incumbent), "candidate_dir": str(candidate)},
                ensure_ascii=False), encoding="utf-8")
            before = _protected_capture(exp_dir, spec)
            rc = _run_mutation(mutation_script, incumbent, candidate, n, ctx, exp_dir, iterdir)
            after = _protected_capture(exp_dir, spec)
            if before != after:
                _restore_protected(before, after)  # roll back the violation
                ir.reason = "rejected: mutation modified the protected surface"
                _record(history, ir)
                result.iterations.append(ir)
                no_improve += 1
                if patience and no_improve >= patience:
                    result.stopped_by = "no_improvement"
                    break
                continue
            if rc is None or rc != 0:
                ir.reason = f"rejected: mutation_script {'timed out' if rc is None else f'exited {rc}'}"
                _record(history, ir)
                result.iterations.append(ir)
                no_improve += 1
                if patience and no_improve >= patience:
                    result.stopped_by = "no_improvement"
                    break
                continue

        # run the candidate through the pipeline, into this iteration's evidence dir
        iter_ev = iterdir / "evidence"
        run_auto(exp_dir, spec, evidence_dir=iter_ev, working_dir_override=candidate)
        run_inspection(exp_dir, spec, evidence_dir=iter_ev)
        ev_result = run_evaluation(exp_dir, spec, evidence_dir=iter_ev)
        ir.primary_status = ev_result.objective_status
        ir.score = _primary_score(ev_result, primary_track)
        blocking = _count_blocking(iter_ev, block_on_issues)
        ir.issues = blocking

        # promotion decision
        reasons: list[str] = []
        promote = True
        if require_primary and ir.primary_status != "passed":
            promote = False
            reasons.append(f"primary track not passed (status={ir.primary_status})")
        if ir.primary_status == "pending" and not allow_pending:
            promote = False
            reasons.append("evaluation pending (human/llm) and allow_pending is false")
        if blocking > 0:
            promote = False
            reasons.append(f"{blocking} blocking issue(s)")

        if promote:
            shutil.rmtree(incumbent, ignore_errors=True)
            shutil.copytree(candidate, incumbent)
            result.promotions += 1
            ir.promoted = True
            ir.reason = "promoted: candidate met promotion policy"
            improved = (best_score is None
                        or (ir.score is not None and best_score is not None and ir.score > best_score)
                        or (ir.primary_status == "passed" and not incumbent_passed))
            if ir.score is not None and (best_score is None or ir.score > best_score):
                best_score = ir.score
            incumbent_passed = incumbent_passed or (ir.primary_status == "passed")
            no_improve = 0 if improved else no_improve + 1
        else:
            ir.reason = "rejected: " + "; ".join(reasons)
            no_improve += 1

        _record(history, ir)
        result.iterations.append(ir)
        if patience and no_improve >= patience:
            result.stopped_by = "no_improvement"
            break

    result.incumbent_dir = str(incumbent)
    with (opt_dir / "history.jsonl").open("w", encoding="utf-8") as f:
        for rec in history:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return result


def _record(history: list[dict], ir: IterationResult) -> None:
    rec = {"iteration": ir.iteration, "candidate_dir": ir.candidate_dir,
           "primary_status": ir.primary_status, "score": ir.score, "issues": ir.issues,
           "promoted": ir.promoted, "reason": ir.reason, "created_by": "AutoOptimize"}
    history.append(rec)
    # also drop a per-iteration record next to the candidate's evidence
    iterdir = Path(ir.candidate_dir).resolve()
    # candidate_dir is harnesses/candidates/iter-NNN; the iteration json lives under
    # optimization/iterations/iter-NNN.json (sibling tree) — resolve via name
    name = iterdir.name  # iter-NNN
    opt_iters = iterdir.parents[2] / "optimization" / "iterations"
    try:
        opt_iters.mkdir(parents=True, exist_ok=True)
        (opt_iters / f"{name}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    except OSError:
        pass
