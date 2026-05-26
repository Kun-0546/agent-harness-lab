"""Evidence-aware result — infer per-variant evidence level from snapshots.

v0.4 reads facts already persisted in v0.3.0 runtime snapshots and surfaces
them as decision-grade signals in score results and compare reports. No
runtime behavior change; evidence is interpretation, not collection.

Rules summarized (full spec: docs/evidence-aware-result.md):

- local_path is strong if snapshot has runtime_source.source_dir_hash. If
  harness_patch is present, patch_hash must also be present (else medium).
  Absent harness_patch (variant runs raw source) does NOT downgrade.

- git_repo is strong if snapshot has runtime_source.commit_sha AND
  source_dir_hash. If harness_patch is present, patch_hash must also be
  present (else medium). Absent harness_patch does NOT downgrade.

- legacy_connect upgrades from weak to medium when any of
  materials/{runtime-evidence.md, harness-evidence.md, cloud-evidence.md}
  exists. Existence-only — file contents are never parsed.

- Missing snapshot, corrupt snapshot, unrecognized runtime_source.type all
  resolve to unknown. Compare flow degrades gracefully.

Pure stdlib. No external dependencies.
"""
from __future__ import annotations

import json
from pathlib import Path

LEVEL_STRONG = "strong"
LEVEL_MEDIUM = "medium"
LEVEL_WEAK = "weak"
LEVEL_UNKNOWN = "unknown"
LEVELS = (LEVEL_STRONG, LEVEL_MEDIUM, LEVEL_WEAK, LEVEL_UNKNOWN)

MATERIALS_EVIDENCE_FILES = (
    "runtime-evidence.md",
    "harness-evidence.md",
    "cloud-evidence.md",
)

_WARNING_WEAK_UNKNOWN = (
    "weak/unknown evidence may be behavioral-only or missing metadata; "
    "do not treat this as fully reproducible harness comparison"
)
_NOTE_LEVELS_DIFFER = (
    "evidence levels differ; comparison is useful but not equally grounded"
)


def _detect_materials_evidence(materials_dir: Path | None) -> list[str]:
    """Return names of evidence files present in materials_dir, existence-only."""
    if materials_dir is None or not materials_dir.exists():
        return []
    return [n for n in MATERIALS_EVIDENCE_FILES if (materials_dir / n).exists()]


def infer_evidence_from_snapshot(snapshot_dict: dict | None,
                                  materials_dir: Path | None) -> dict:
    """Infer evidence level for a single variant from its snapshot dict.

    Returns a stable, JSON-serializable dict:
        {"level", "runtime_source_type", "snapshot_id", "snapshot_available",
         "materials_evidence", "reasons"}

    snapshot_dict=None → unknown (snapshot file missing or unreadable).
    """
    materials_evidence = _detect_materials_evidence(materials_dir)

    if snapshot_dict is None:
        return {
            "level": LEVEL_UNKNOWN,
            "runtime_source_type": None,
            "snapshot_id": None,
            "snapshot_available": False,
            "materials_evidence": materials_evidence,
            "reasons": ["snapshot file missing or unreadable"],
        }

    snapshot_id = snapshot_dict.get("snapshot_id")
    rs = snapshot_dict.get("runtime_source") or {}
    rs_type = rs.get("type")
    harness_patch = snapshot_dict.get("harness_patch")  # None for legacy

    common = {
        "snapshot_id": snapshot_id,
        "snapshot_available": True,
        "materials_evidence": materials_evidence,
        "runtime_source_type": rs_type,
    }

    if rs_type == "local_path":
        return _infer_local_path(rs, harness_patch, common)
    if rs_type == "git_repo":
        return _infer_git_repo(rs, harness_patch, common)
    if rs_type == "legacy_connect":
        return _infer_legacy(materials_evidence, common)
    return {
        **common,
        "level": LEVEL_UNKNOWN,
        "reasons": [f"unrecognized runtime_source.type={rs_type!r}"],
    }


def _infer_local_path(rs: dict, harness_patch: dict | None, common: dict) -> dict:
    """local_path: source_dir_hash required for strong; patch_hash only if patch declared."""
    if not rs.get("source_dir_hash"):
        return {**common, "level": LEVEL_MEDIUM,
                "reasons": ["local_path missing source_dir_hash"]}
    if harness_patch is not None:
        if not harness_patch.get("patch_hash"):
            return {**common, "level": LEVEL_MEDIUM,
                    "reasons": ["local_path harness_patch present but missing patch_hash"]}
        return {**common, "level": LEVEL_STRONG,
                "reasons": ["local_path with source_dir_hash and patch_hash"]}
    return {**common, "level": LEVEL_STRONG,
            "reasons": ["local_path with source_dir_hash (no harness_patch declared)"]}


def _infer_git_repo(rs: dict, harness_patch: dict | None, common: dict) -> dict:
    """git_repo: commit_sha + source_dir_hash required; patch_hash only if patch declared."""
    missing = []
    if not rs.get("source_dir_hash"):
        missing.append("source_dir_hash")
    if not rs.get("commit_sha"):
        missing.append("commit_sha")
    if missing:
        return {**common, "level": LEVEL_MEDIUM,
                "reasons": [f"git_repo missing {', '.join(missing)}"]}
    if harness_patch is not None:
        if not harness_patch.get("patch_hash"):
            return {**common, "level": LEVEL_MEDIUM,
                    "reasons": ["git_repo harness_patch present but missing patch_hash"]}
        return {**common, "level": LEVEL_STRONG,
                "reasons": ["git_repo with commit_sha, source_dir_hash, and patch_hash"]}
    return {**common, "level": LEVEL_STRONG,
            "reasons": ["git_repo with commit_sha and source_dir_hash (no harness_patch declared)"]}


def _infer_legacy(materials_evidence: list[str], common: dict) -> dict:
    """legacy_connect: weak by default; any materials evidence file → medium."""
    if materials_evidence:
        return {**common, "level": LEVEL_MEDIUM,
                "reasons": [
                    f"legacy_connect with materials evidence: "
                    f"{', '.join(materials_evidence)}"]}
    return {**common, "level": LEVEL_WEAK,
            "reasons": ["legacy_connect with no materials evidence files"]}


def _load_snapshot_for_variant(exp_dir: Path, run_id: str,
                                variant_id: str) -> dict | None:
    """Load results/snapshots/<run_id>/<variant_id>.json. None on missing/corrupt."""
    if not run_id:
        return None
    path = exp_dir / "results" / "snapshots" / run_id / f"{variant_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def _run_id_from_filename(run_filename: str) -> str:
    """run-20260525-160000.json → run-20260525-160000. Empty stays empty."""
    if not run_filename:
        return ""
    if run_filename.endswith(".json"):
        return run_filename[:-5]
    return run_filename


def _build_summary(counts: dict[str, int]) -> dict:
    """Build summary block with 3-tier warning/note per spec §5.1."""
    weak_or_unknown = counts[LEVEL_WEAK] + counts[LEVEL_UNKNOWN]
    distinct_levels = sum(1 for c in counts.values() if c > 0)
    warning = None
    note = None
    if weak_or_unknown > 0:
        warning = _WARNING_WEAK_UNKNOWN
    elif distinct_levels > 1:
        note = _NOTE_LEVELS_DIFFER
    return {"levels": dict(counts), "warning": warning, "note": note}


def _empty_summary() -> dict:
    return _build_summary({l: 0 for l in LEVELS})


def summarize_evidence_for_run(run_records: list,
                                run_id: str,
                                exp_dir: Path) -> dict:
    """Build full evidence summary from run records + run_id + exp_dir.

    Used by:
    - score flow: right after run records are loaded, before writing score JSON.
    - compare flow fallback: when score JSON lacks evidence and we need to
      recompute from the underlying run records.

    Returns the v0.4 evidence summary dict: {variants, summary}.
    """
    materials_dir = exp_dir / "materials"

    variants_out: dict[str, dict] = {}
    counts = {l: 0 for l in LEVELS}

    seen: set = set()
    for rec in run_records:
        if not isinstance(rec, dict):
            continue
        vid = rec.get("version_id", "")
        if not vid or vid in seen:
            continue
        seen.add(vid)

        snapshot_dict = _load_snapshot_for_variant(exp_dir, run_id, vid)
        evidence = infer_evidence_from_snapshot(snapshot_dict, materials_dir)
        variants_out[vid] = evidence
        counts[evidence["level"]] += 1

    return {
        "variants": variants_out,
        "summary": _build_summary(counts),
    }


def summarize_evidence_for_score(score_data: dict, exp_dir: Path) -> dict:
    """Compare-flow fallback when score JSON lacks evidence.

    Two paths:
    1. Preferred: load run-*.json referenced by score_data["run"], derive
       run_id from the filename, defer to summarize_evidence_for_run which
       inspects per-variant snapshots. If this yields any variants
       (including all-unknown when snapshot files are missing), return it.
    2. Synthesis fallback: if the run file itself is missing/corrupt OR the
       resulting summary has no variants, synthesize one unknown entry per
       unique version_id in score_data["scores"]. This guarantees the
       compare report Evidence section always renders and triggers a
       warning when evidence metadata is unavailable (spec §6).

    Never raises. Compare flow stays graceful.
    """
    materials_dir = exp_dir / "materials"
    run_name = score_data.get("run", "")

    if run_name:
        run_path = exp_dir / "results" / run_name
        try:
            run_records = json.loads(run_path.read_text(encoding="utf-8"))
            result = summarize_evidence_for_run(
                run_records, _run_id_from_filename(run_name), exp_dir)
            if result["variants"]:
                return result
        except (FileNotFoundError, json.JSONDecodeError,
                UnicodeDecodeError, OSError):
            pass

    return _synthesize_unknown_from_score(score_data, materials_dir)


def _synthesize_unknown_from_score(score_data: dict,
                                    materials_dir: Path) -> dict:
    """Build an unknown-evidence summary from a score's `scores` array.

    Used as the last-resort fallback in summarize_evidence_for_score when
    the underlying run file is unavailable. Each unique `version_id` in
    score_data["scores"] gets one entry with level=unknown and a reason
    pointing to the missing metadata.

    Empty `scores` (or score_data without the key) yields an empty
    variants dict — there is nothing to synthesize from.
    """
    materials_evidence = _detect_materials_evidence(materials_dir)
    score_entries = score_data.get("scores", []) or []

    variants_out: dict[str, dict] = {}
    counts = {l: 0 for l in LEVELS}
    seen: set = set()

    for entry in score_entries:
        if not isinstance(entry, dict):
            continue
        vid = entry.get("version_id", "")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        variants_out[vid] = {
            "level": LEVEL_UNKNOWN,
            "runtime_source_type": None,
            "snapshot_id": None,
            "snapshot_available": False,
            "materials_evidence": materials_evidence,
            "reasons": [
                "score result has no evidence metadata and run/snapshot "
                "could not be loaded"
            ],
        }
        counts[LEVEL_UNKNOWN] += 1

    return {"variants": variants_out, "summary": _build_summary(counts)}


def evidence_warning(evidence_summary: dict | None) -> dict:
    """Extract {warning, note} from a summary; either may be None.

    Used by CLI for compact stdout surfacing.
    """
    summary = (evidence_summary or {}).get("summary", {})
    return {"warning": summary.get("warning"), "note": summary.get("note")}
