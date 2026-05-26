"""Doc consistency tests — catch docs/sample/CLI drift via semantic anchors.

Spec: docs/product-reliability-evidence-hardening.md §5.2.

These tests check semantic anchors (file presence, link targets, banner
detection, behavioral claims matching code), NOT exact prose. Tests should
not break on cosmetic wording changes; they should break when the
underlying claim is no longer true.

Skipped from scans (per Kun open-question lock #6):
- docs/archive/**
- docs/handoffs/**
- any docs/*.md whose first 30 lines contain a deprecation banner
  ("已被", "deprecated", "historical", "v0.2.0 时代", "v2-minimal", etc.)
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
EXAMPLES_DIR = REPO_ROOT / "examples"

# Banner phrases that mark a doc as historical / deprecated. If any appears
# in the first 30 lines of a doc, the doc is excluded from drift scans.
_DEPRECATION_BANNERS = (
    "已被",
    "v0.2.0 时代",
    "v2-minimal-spec",  # body refers to v2-minimal era
    "v2-minimal 时代",
    "v1 / HDL",
    "v2+ 长期方向",
    "deprecated",
    "Deprecated",
    "DEPRECATED",
    "historical",
    "Historical",
    "HISTORICAL",
)
_DEPRECATION_PATH_PARTS = ("archive", "handoffs")


def _is_historical(md_path: Path) -> bool:
    """True if md_path should be excluded from current-surface drift scans."""
    if any(part in _DEPRECATION_PATH_PARTS for part in md_path.parts):
        return True
    if not md_path.exists():
        return False
    try:
        head = "\n".join(md_path.read_text(encoding="utf-8").splitlines()[:30])
    except (OSError, UnicodeDecodeError):
        return False
    return any(b in head for b in _DEPRECATION_BANNERS)


# Matches markdown link [text](path). Text and path can contain most chars
# except the structural ones; the text portion is allowed to embed
# backticks (real links like [`name`](path) are common in our docs).
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _extract_links(md_text: str) -> list[tuple[str, str]]:
    """Return list of (text, path) for each markdown link in md_text.

    Skips lines inside fenced code blocks. Does NOT strip inline code
    spans — that would eat backticks legitimately inside link text like
    [`name`](path). False-positive matches inside inline-code regions
    (e.g., `[text](path)` used as documentation) are filtered out
    downstream by _is_external_or_anchor's path-content checks.
    """
    results: list[tuple[str, str]] = []
    in_fenced = False
    for line in md_text.split("\n"):
        if _FENCE_RE.match(line):
            in_fenced = not in_fenced
            continue
        if in_fenced:
            continue
        for match in _LINK_RE.finditer(line):
            results.append((match.group(1), match.group(2)))
    return results


def _is_external_or_anchor(path: str) -> bool:
    """Skip external URLs, mailto:, anchor-only links, and bracket-paren
    constructs that aren't really links.

    Real markdown link paths have one of: a scheme (http/https/mailto),
    an anchor prefix (#), a path separator (/), an extension dot (.).
    Paths without any of those are almost certainly false-positive
    matches of inline-code constructs like `[text](path)` or
    `[array](description)` — the markdown parser would treat them as
    links too, but they don't point anywhere useful, and our test would
    just emit noise. Pragmatic filter: require one of the markers.

    Spaces in the path are also rejected — real markdown link paths
    URL-encode spaces, so a literal space signals
    `[array, with, brackets](free text in parens)` adjacency.
    """
    p = path.strip()
    if not p:
        return True
    if (p.startswith("http://") or p.startswith("https://")
            or p.startswith("mailto:") or p.startswith("#")):
        return True
    if " " in p:
        return True
    # Bare-word paths (no `/`, no `.`) are almost always false positives.
    if "/" not in p and "." not in p:
        return True
    return False


def _resolve_link(src_md_path: Path, link_path: str) -> Path:
    """Resolve a relative link target. Strip #anchor and ?query."""
    cleaned = link_path.split("#", 1)[0].split("?", 1)[0].strip()
    return (src_md_path.parent / cleaned).resolve()


def _current_surface_md_files() -> list[Path]:
    """Return paths to docs we treat as the current product surface."""
    candidates = []
    for top in ("README.md", "README_CN.md"):
        p = REPO_ROOT / top
        if p.exists():
            candidates.append(p)
    if DOCS_DIR.exists():
        for p in sorted(DOCS_DIR.glob("*.md")):
            if not _is_historical(p):
                candidates.append(p)
    # Include README files inside examples/* (not the deep example trees)
    for p in sorted(EXAMPLES_DIR.glob("*/README.md")):
        candidates.append(p)
    return candidates


# ===========================================================================
# Check 1 + 2: docs/README.md current-mainline links + evidence-guide linked
# ===========================================================================


class TestDocsReadmeMainlineLinks(unittest.TestCase):

    def test_docs_readme_exists_and_is_readable(self):
        p = DOCS_DIR / "README.md"
        self.assertTrue(p.exists(), f"{p} not found")
        text = p.read_text(encoding="utf-8")
        self.assertGreater(len(text), 100, "docs/README.md is suspiciously short")

    def test_docs_readme_mainline_links_resolve(self):
        """Every relative-path link in docs/README.md must resolve to a real
        file or directory. External / anchor-only links are skipped."""
        readme = DOCS_DIR / "README.md"
        text = readme.read_text(encoding="utf-8")
        broken: list[tuple[str, str, str]] = []
        for link_text, link_path in _extract_links(text):
            if _is_external_or_anchor(link_path):
                continue
            target = _resolve_link(readme, link_path)
            if not target.exists():
                broken.append((link_text, link_path, str(target)))
        self.assertFalse(broken,
                          "Broken links in docs/README.md:\n  " +
                          "\n  ".join(f"[{t}]({p}) → {r}" for t, p, r in broken))


class TestEvidenceGuideLinked(unittest.TestCase):

    def test_evidence_guide_linked_from_docs_readme(self):
        """C1 deliverable: evidence-guide.md must be reachable from
        docs/README.md (any link target ending with 'evidence-guide.md')."""
        readme = DOCS_DIR / "README.md"
        text = readme.read_text(encoding="utf-8")
        targets = [link_path for _, link_path in _extract_links(text)
                   if not _is_external_or_anchor(link_path)]
        normalized = [t.split("#", 1)[0].split("?", 1)[0].strip("/")
                      for t in targets]
        self.assertTrue(
            any(n.endswith("evidence-guide.md") for n in normalized),
            f"docs/README.md does not link evidence-guide.md. "
            f"Found link targets: {normalized}")


# ===========================================================================
# Check 3: key specs reachable from current docs nav
# ===========================================================================


class TestKeySpecsReachableFromDocsNav(unittest.TestCase):

    REQUIRED_SPEC_FILENAMES = (
        "runtime-probe-mvp.md",
        "harness-package-mvp.md",
        "product-flow-completion.md",
        "evidence-guide.md",
    )

    def test_required_specs_linked_from_docs_readme(self):
        """Each required spec must be linked at least once from
        docs/README.md (the canonical nav)."""
        readme = DOCS_DIR / "README.md"
        text = readme.read_text(encoding="utf-8")
        targets = [link_path for _, link_path in _extract_links(text)
                   if not _is_external_or_anchor(link_path)]
        normalized = [t.split("#", 1)[0].split("?", 1)[0].strip("/")
                      for t in targets]
        missing = [name for name in self.REQUIRED_SPEC_FILENAMES
                   if not any(n.endswith(name) for n in normalized)]
        self.assertFalse(missing,
                          f"docs/README.md mainline list is missing links to: "
                          f"{missing}. Found targets: {sorted(set(normalized))}")

    def test_required_spec_files_actually_exist(self):
        """Linked-from-nav specs must also exist on disk."""
        for name in self.REQUIRED_SPEC_FILENAMES:
            self.assertTrue((DOCS_DIR / name).exists(),
                              f"{DOCS_DIR / name} not found")


# ===========================================================================
# Check 4: sample-workspace simulator.md claim matches stub_simulator behavior
# ===========================================================================


class TestSimulatorMdMatchesStubBehavior(unittest.TestCase):

    def test_simulator_md_turn_count_matches_stub_followups(self):
        """sample-workspace simulator.md asserts a specific turn count
        per case. That count must equal 1 (case opening) +
        len(_STUB_FOLLOWUPS) from src/agent_harness_lab/simulator.py.

        This caught the v0.7 release blocker (sample-workspace simulator.md
        falsely claimed single-turn behavior). The check is a guardrail
        against the same class of drift reappearing.
        """
        # Import after the test starts so the failure is clear if src is
        # broken (vs an import error at collection time).
        import sys
        src = str(REPO_ROOT / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from agent_harness_lab.simulator import _STUB_FOLLOWUPS  # type: ignore

        expected_turns = 1 + len(_STUB_FOLLOWUPS)

        sim_md = (REPO_ROOT / "examples" / "sample-workspace"
                  / "experiments" / "001-faq-conciseness" / "simulator.md")
        self.assertTrue(sim_md.exists(), f"{sim_md} not found")
        text = sim_md.read_text(encoding="utf-8")

        # Semantic anchor: the file mentions the expected turn count as a
        # standalone number adjacent to a turn-related word. We deliberately
        # do NOT match a specific Chinese / English phrase so the test
        # tolerates wording edits.
        digit = str(expected_turns)
        patterns = (
            rf"{digit}\s*轮",
            rf"{digit}\s*turn",
            rf"{digit}-turn",
            rf"\b{digit}\s+turns\b",
        )
        matched = any(re.search(p, text, re.IGNORECASE) for p in patterns)
        self.assertTrue(
            matched,
            f"sample-workspace simulator.md does not mention the expected "
            f"turn count ({expected_turns}) in a 'N 轮' / 'N turn' shape. "
            f"_STUB_FOLLOWUPS currently has {len(_STUB_FOLLOWUPS)} entries → "
            f"1 + {len(_STUB_FOLLOWUPS)} = {expected_turns} turns per case. "
            f"Update simulator.md if you changed _STUB_FOLLOWUPS, or vice "
            f"versa. simulator.md head:\n{text[:600]!r}")


# ===========================================================================
# Check 5: committed sample workspace is artifact-clean
# ===========================================================================


class TestSampleWorkspaceCleanliness(unittest.TestCase):

    def test_no_generated_artifacts_in_committed_sample(self):
        """Mirrors tests/test_sample_workspace_e2e.py's cleanliness check
        with broader path coverage for v0.8 drift detection."""
        exp = (REPO_ROOT / "examples" / "sample-workspace"
               / "experiments" / "001-faq-conciseness")
        forbidden = (
            exp / "results",
            exp / "probe-results",
            exp / "snapshots",  # never auto-created at exp root in current
                                # workflow, but flagged defensively
            exp / "materials" / "runtime-evidence.md",
        )
        # Glob-level checks (any matching file is a problem).
        forbidden_glob_parents = (
            (exp, "run-*.json"),
            (exp, "score-*.json"),
            (exp, "compare-*.md"),
        )

        offenders = []
        for path in forbidden:
            if path.exists():
                offenders.append(str(path.relative_to(REPO_ROOT)))
        for parent, pattern in forbidden_glob_parents:
            if parent.exists():
                for hit in parent.glob(pattern):
                    offenders.append(str(hit.relative_to(REPO_ROOT)))

        self.assertFalse(
            offenders,
            f"committed sample workspace contains generated artifacts that "
            f"should be gitignored:\n  " + "\n  ".join(offenders))


# ===========================================================================
# Check 6 + 7: evidence examples exist + carry limitation language
# ===========================================================================


class TestEvidenceExamples(unittest.TestCase):

    EVIDENCE_EXAMPLES_DIR = EXAMPLES_DIR / "evidence-examples"
    EXPECTED_FILES = (
        "README.md",
        "runtime-evidence.md",
        "harness-evidence.md",
        "cloud-evidence.md",
    )

    def test_evidence_examples_directory_and_files_present(self):
        self.assertTrue(self.EVIDENCE_EXAMPLES_DIR.is_dir(),
                          f"{self.EVIDENCE_EXAMPLES_DIR} is not a directory")
        for name in self.EXPECTED_FILES:
            path = self.EVIDENCE_EXAMPLES_DIR / name
            self.assertTrue(path.exists(), f"{path} not found")
            self.assertGreater(
                path.stat().st_size, 100,
                f"{path} is suspiciously short ({path.stat().st_size} bytes)")

    def test_evidence_examples_carry_limitation_language(self):
        """Each evidence example file (not the README index) must include:
        - a 'not cloud attestation' negation, AND
        - a 'cannot reach strong' / 'ceiling at medium' equivalent.
        Phrasing is checked loosely so cosmetic edits don't trip the test.
        """
        evidence_files = ("runtime-evidence.md", "harness-evidence.md",
                          "cloud-evidence.md")
        cloud_attestation_pattern = re.compile(
            r"\b(?:not|isn['’]?t|never)\s+cloud\s+attestation\b",
            re.IGNORECASE)
        ceiling_patterns = (
            re.compile(r"cannot\s+reach\s+[`]?strong[`]?", re.IGNORECASE),
            re.compile(r"cannot\s+become\s+[`]?strong[`]?", re.IGNORECASE),
            re.compile(r"ceiling\s+at\s+[`]?medium[`]?", re.IGNORECASE),
            re.compile(r"never\s+reach[es]?\s+[`]?strong[`]?", re.IGNORECASE),
        )
        for name in evidence_files:
            path = self.EVIDENCE_EXAMPLES_DIR / name
            text = path.read_text(encoding="utf-8")
            self.assertRegex(
                text, cloud_attestation_pattern,
                f"{path.name} is missing a 'NOT cloud attestation' "
                f"negation. Add a disclosure clause similar to "
                f"'supplied evidence is not cloud attestation'.")
            ceiling_match = any(p.search(text) for p in ceiling_patterns)
            self.assertTrue(
                ceiling_match,
                f"{path.name} is missing a 'cannot reach strong' / "
                f"'ceiling at medium' equivalent. Supplied evidence "
                f"templates must be honest that they can never upgrade "
                f"beyond medium.")


# ===========================================================================
# Check 8: dead-link scan across current docs surface (skip historical)
# ===========================================================================


class TestNoDeadInternalLinks(unittest.TestCase):

    def test_no_dead_internal_links_in_current_docs(self):
        """For every link in the current docs surface (README +
        docs/*.md excluding historical + examples/*/README.md), verify
        the target file or directory exists.

        Skipped per lock #6: docs/archive/, docs/handoffs/, and any
        docs/*.md whose first 30 lines contain a deprecation banner.
        External URLs (http / https / mailto) and anchor-only (#section)
        are also skipped.
        """
        broken: list[tuple[str, str, str]] = []
        for md_path in _current_surface_md_files():
            try:
                text = md_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for link_text, link_path in _extract_links(text):
                if _is_external_or_anchor(link_path):
                    continue
                target = _resolve_link(md_path, link_path)
                if not target.exists():
                    broken.append((
                        str(md_path.relative_to(REPO_ROOT)),
                        link_path,
                        str(target.relative_to(REPO_ROOT)) if
                          REPO_ROOT in target.parents else str(target),
                    ))
        self.assertFalse(
            broken,
            "Dead internal links in current docs surface:\n  " +
            "\n  ".join(f"in {src}: [{p}] → {r}" for src, p, r in broken))


if __name__ == "__main__":
    unittest.main()
