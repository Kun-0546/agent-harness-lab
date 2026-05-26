"""v0.10 Release-Candidate (RC) invariants.

Five strict structural / drift-detector checks that defend the
v0.10 OSS-readiness freeze. Run as part of the regular pytest
suite (default + ``-W error::ResourceWarning`` strict).

Invariants:

1. Required public-facing files exist (top-level governance + key
   docs that any first-time public visitor will land on).
2. README.md ↔ README_CN.md section-anchor parity: same set of
   major H2 anchors, same Auto-as-deferred / no-public-launch
   posture, same command-cheatsheet content.
3. No unresolved TODO / XXX / FIXME markers in current-surface
   docs. Banner-tagged historical / archive / handoff docs are
   skipped (reuse `test_doc_consistency.py` conventions).
   Allowed: contextual mentions inside fenced code blocks +
   wording like "todo list" / "to-do" that is not a marker.
4. CHANGELOG section ordering matches `git tag --list`
   (descending version order); `[Unreleased]` exists as a
   placeholder; no v0.X section claims to be "shipped" without
   a corresponding tag.
5. No broken internal links across the current-surface doc set
   (reuse the v0.8 link-resolution helper in
   `test_doc_consistency.py`).

Spec: ``docs/open-source-readiness-freeze.md`` §17 + Q6 lock.
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"


# ---------------------------------------------------------------------------
# Invariant 1 — required public-facing files exist
# ---------------------------------------------------------------------------


class TestRequiredPublicFilesExist(unittest.TestCase):
    """The files any first-time public visitor will encounter."""

    REQUIRED = (
        REPO_ROOT / "README.md",
        REPO_ROOT / "README_CN.md",
        REPO_ROOT / "LICENSE",
        REPO_ROOT / "CONTRIBUTING.md",
        REPO_ROOT / "SECURITY.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "pyproject.toml",
        DOCS_DIR / "README.md",
        DOCS_DIR / "public-launch-checklist.md",
        DOCS_DIR / "open-source-readiness-freeze.md",
    )

    def test_each_required_file_exists(self):
        missing = [str(p.relative_to(REPO_ROOT))
                   for p in self.REQUIRED if not p.is_file()]
        self.assertFalse(missing,
                          f"Required public-facing files missing: "
                          f"{missing}")


# ---------------------------------------------------------------------------
# Invariant 2 — README ↔ README_CN parity
# ---------------------------------------------------------------------------


# Numbered (§1–§9) anchors must match by number; section labels can differ.
# E.g. "## 1. What is Agent Harness Lab?" (EN) ↔ "## 1. Agent Harness Lab 是什么?" (CN)
_NUMBERED_HEADING_RE = re.compile(r"^## (\d+)\. ", re.MULTILINE)


def _extract_numbered_section_ids(md_path: Path) -> set[str]:
    text = md_path.read_text(encoding="utf-8")
    return set(_NUMBERED_HEADING_RE.findall(text))


def _h2_headings(md_path: Path) -> list[str]:
    """Return the list of H2 heading texts (without '## ' prefix)."""
    text = md_path.read_text(encoding="utf-8")
    return [m.group(1) for m in re.finditer(r"^## (.+)$", text, re.MULTILINE)]


class TestReadmeEnCnParity(unittest.TestCase):
    """v0.10 RC: README + README_CN must stay synchronized at the
    section-anchor level. Wording per-section may differ; structural
    skeleton must not drift."""

    def setUp(self):
        self.en = REPO_ROOT / "README.md"
        self.cn = REPO_ROOT / "README_CN.md"

    def test_numbered_section_ids_match(self):
        """Every §N in EN must have a matching §N in CN."""
        en_ids = _extract_numbered_section_ids(self.en)
        cn_ids = _extract_numbered_section_ids(self.cn)
        self.assertEqual(en_ids, cn_ids,
                         f"README EN/CN numbered-section drift: "
                         f"EN only={en_ids - cn_ids}, "
                         f"CN only={cn_ids - en_ids}")

    def test_h2_heading_count_matches(self):
        """Same number of H2 sections total (numbered + named)."""
        en = _h2_headings(self.en)
        cn = _h2_headings(self.cn)
        self.assertEqual(
            len(en), len(cn),
            f"README EN has {len(en)} H2 sections; "
            f"README_CN has {len(cn)}. Section drift.")

    def test_auto_deferred_language_present_in_both(self):
        """Q3 lock: Auto must appear in README §9 (or near it) framed
        as deferred / not next / not v0.10, in BOTH EN and CN."""
        en_text = self.en.read_text(encoding="utf-8")
        cn_text = self.cn.read_text(encoding="utf-8")
        # The substring 'Auto' appears; AND a deferral marker.
        for label, text in (("EN", en_text), ("CN", cn_text)):
            self.assertIn("Auto", text,
                          f"README {label} should mention Auto mode")
            # Must use a deferral framing — at least one of:
            #   "deferred"  | "post-open-source" | "v1.x" | "推到"
            deferral_markers = ("deferred", "post-open-source",
                                "v1.x", "推到", "post-OSS")
            self.assertTrue(
                any(marker in text for marker in deferral_markers),
                f"README {label} must frame Auto as deferred / "
                f"post-open-source / v1.x (none of {deferral_markers} "
                f"found)")

    def test_no_public_launch_claim_in_either(self):
        """Q3 + spec §6 + Q8 lock: README must not imply public
        launch is imminent / done / automatic."""
        for label, p in (("EN", self.en), ("CN", self.cn)):
            text = p.read_text(encoding="utf-8")
            forbidden = (
                "open source soon",
                "ready for public",
                "production-ready",
                "公开发布",
                "已开源",
                "即将开源",
            )
            for needle in forbidden:
                self.assertNotIn(
                    needle, text,
                    f"README {label} contains banned 'imminent public "
                    f"launch' phrase: {needle!r}")


# ---------------------------------------------------------------------------
# Invariant 3 — no unresolved TODO / XXX / FIXME in current-surface docs
# ---------------------------------------------------------------------------


# Conservative pattern: word-boundary, all-caps.
#
# A marker counts as "unresolved" only when it looks like an actual
# action-item embedded in prose. The following do NOT count and are
# stripped before the search:
#
# - Markers inside fenced code blocks (whole lines containing example
#   file content, command snippets, etc.).
# - Markers inside inline code spans (`TODO`, `FIXME`) — these are
#   typically scanner-name references, not action items.
# - Markers inside double-quoted strings ("TODO", "FIXME") — same.
# - Lines that mention TWO OR MORE of the marker words (e.g.
#   "TODO/XXX/FIXME" or "no TODO, XXX, or FIXME left") — these are
#   meta-descriptions of "what we scan for", not action items.
_MARKER_RE = re.compile(r"\b(TODO|XXX|FIXME)\b")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
# Strip inline code spans (`...`) and "..." quoted spans before scanning.
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_DOUBLE_QUOTED_RE = re.compile(r'"[^"\n]*"')

# Banner phrases mark historical docs; reuse the v0.8 convention.
_DEPRECATION_BANNERS = (
    "已被",
    "v0.2.0 时代",
    "v2-minimal-spec",
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
    if any(part in _DEPRECATION_PATH_PARTS for part in md_path.parts):
        return True
    if not md_path.exists():
        return False
    try:
        head = "\n".join(
            md_path.read_text(encoding="utf-8").splitlines()[:30])
    except (OSError, UnicodeDecodeError):
        return False
    return any(b in head for b in _DEPRECATION_BANNERS)


def _scan_markers(md_path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_no, marker, full_line) for lines that look
    like a real action-item marker.

    Skips:
    - lines inside fenced code blocks
    - markers inside inline code spans (backticks)
    - markers inside double-quoted strings
    - lines that mention 2+ marker words (meta-descriptions of the
      scanner itself, e.g. "no TODO/XXX/FIXME")
    """
    findings: list[tuple[int, str, str]] = []
    in_fenced = False
    try:
        lines = md_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return findings
    for i, line in enumerate(lines, start=1):
        if _FENCE_RE.match(line):
            in_fenced = not in_fenced
            continue
        if in_fenced:
            continue
        # Strip inline code spans and double-quoted strings so embedded
        # marker names there do not trigger the scan.
        scrubbed = _INLINE_CODE_RE.sub(" ", line)
        scrubbed = _DOUBLE_QUOTED_RE.sub(" ", scrubbed)
        matches = list(_MARKER_RE.finditer(scrubbed))
        if not matches:
            continue
        distinct_markers = {m.group(1) for m in matches}
        # A meta-description of the scanner (e.g.
        # "TODO/XXX/FIXME left in the docs") names 2+ markers in the
        # same line. Don't flag those.
        if len(distinct_markers) > 1:
            continue
        m = matches[0]
        findings.append((i, m.group(1), line.strip()))
    return findings


class TestNoUnresolvedMarkersInCurrentDocs(unittest.TestCase):
    """v0.10 RC: any TODO / XXX / FIXME marker in a current-surface
    doc is an unresolved action item; RC means action items
    resolved. Banner-tagged HISTORICAL and archive/handoffs paths
    are excluded.

    Allowed exceptions: markers inside fenced code blocks (example
    file content / commands). Otherwise: fail with the file + line
    listed.
    """

    def test_current_surface_docs_have_no_unresolved_markers(self):
        candidates: list[Path] = []
        for top in ("README.md", "README_CN.md", "CHANGELOG.md",
                    "CONTRIBUTING.md", "SECURITY.md"):
            p = REPO_ROOT / top
            if p.exists():
                candidates.append(p)
        if DOCS_DIR.exists():
            for p in sorted(DOCS_DIR.glob("*.md")):
                if not _is_historical(p):
                    candidates.append(p)

        offenders: list[str] = []
        for p in candidates:
            findings = _scan_markers(p)
            for line_no, marker, full_line in findings:
                offenders.append(
                    f"{p.relative_to(REPO_ROOT)}:{line_no}: "
                    f"{marker} → {full_line!r}")

        self.assertFalse(offenders,
                          "Unresolved TODO/XXX/FIXME markers in "
                          "current-surface docs (each is an RC "
                          "blocker):\n  " + "\n  ".join(offenders))


# ---------------------------------------------------------------------------
# Invariant 4 — CHANGELOG ↔ tag order coherent
# ---------------------------------------------------------------------------


_CHANGELOG_SECTION_RE = re.compile(
    r"^## \[(?P<version>[^\]]+)\](?:\s*-\s*(?P<date>\S+))?",
    re.MULTILINE)


def _parse_changelog_versions() -> list[str]:
    """Return CHANGELOG version labels in the order they appear,
    skipping the literal 'Unreleased' placeholder."""
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return [m.group("version") for m in _CHANGELOG_SECTION_RE.finditer(text)
            if m.group("version").lower() != "unreleased"]


_PYPROJECT_VERSION_RE = re.compile(
    r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def _read_pyproject_version() -> str | None:
    """Read the ``version = "X.Y.Z"`` line from pyproject.toml.

    Returns ``None`` if the file or field can't be read.
    """
    p = REPO_ROOT / "pyproject.toml"
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = _PYPROJECT_VERSION_RE.search(text)
    return m.group(1) if m else None


def _git_tags_descending_semver() -> list[str]:
    """Return git tags sorted descending by semver (strip leading 'v')."""
    result = subprocess.run(
        ["git", "tag", "--list"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    raw = [t.strip() for t in result.stdout.splitlines() if t.strip()]
    # Keep only vN.N(.N)* style tags.
    semver_re = re.compile(r"^v\d+\.\d+(?:\.\d+)?$")
    semver_tags = [t for t in raw if semver_re.match(t)]
    semver_tags.sort(
        key=lambda t: tuple(int(p) for p in t.lstrip("v").split(".")),
        reverse=True,
    )
    return [t.lstrip("v") for t in semver_tags]


class TestChangelogTagOrder(unittest.TestCase):
    """v0.10 RC: CHANGELOG section ordering must match the
    descending tag order. [Unreleased] must exist. No future
    versions claimed-as-shipped."""

    def test_unreleased_section_exists(self):
        text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("[Unreleased]", text,
                      "CHANGELOG.md must contain an [Unreleased] "
                      "placeholder section (Keep-a-Changelog 1.1).")

    def test_changelog_subset_of_tags(self):
        """Every CHANGELOG version must have a matching git tag,
        with one allowed exception: a release-prep transient state
        in which the most recent CHANGELOG version matches the
        current ``pyproject.toml`` version but has not been tagged
        yet (the tag will be created in the next step of the
        release cycle, pointing at the release-prep commit).

        v0.10 explicitly allows tags that pre-date the
        Keep-a-Changelog adoption (v0.1.0 / v0.2.0) to lack a
        CHANGELOG entry. The inverse direction (CHANGELOG entry
        without a tag) is a hard fail EXCEPT for that one
        release-prep transient.
        """
        cl_versions = set(_parse_changelog_versions())
        tag_versions = set(_git_tags_descending_semver())
        extra_in_changelog = cl_versions - tag_versions
        if not extra_in_changelog:
            return
        # Allow exactly one transient: highest CHANGELOG version
        # matches the pyproject version (release-prep just landed,
        # tag step pending).
        pyproject_version = _read_pyproject_version()
        if (extra_in_changelog == {pyproject_version}
                and pyproject_version in cl_versions):
            # Release-prep transient — allowed.
            return
        self.assertFalse(
            extra_in_changelog,
            f"CHANGELOG has version sections without matching git "
            f"tags: {sorted(extra_in_changelog)}. Either tag them "
            f"or move them back to [Unreleased].")

    def test_changelog_descending_semver_order(self):
        """CHANGELOG version sections must appear in descending
        semver order. Mismatch indicates a release-prep slipped
        a section into the wrong place."""
        cl = _parse_changelog_versions()
        sorted_desc = sorted(
            cl,
            key=lambda v: tuple(int(p) for p in v.split(".")),
            reverse=True,
        )
        self.assertEqual(
            cl, sorted_desc,
            f"CHANGELOG sections out of descending semver order. "
            f"Actual: {cl}; expected: {sorted_desc}.")


# ---------------------------------------------------------------------------
# Invariant 5 — no broken internal links in current-surface docs
# ---------------------------------------------------------------------------


_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")


def _is_external_or_anchor(path: str) -> bool:
    p = path.strip()
    if not p:
        return True
    if (p.startswith("http://") or p.startswith("https://")
            or p.startswith("mailto:") or p.startswith("#")):
        return True
    if " " in p:
        return True
    if "/" not in p and "." not in p:
        return True
    return False


def _resolve_link(src_md_path: Path, link_path: str) -> Path:
    cleaned = link_path.split("#", 1)[0].split("?", 1)[0].strip()
    return (src_md_path.parent / cleaned).resolve()


def _current_surface_md_files() -> list[Path]:
    candidates: list[Path] = []
    for top in ("README.md", "README_CN.md", "CONTRIBUTING.md",
                "SECURITY.md"):
        p = REPO_ROOT / top
        if p.exists():
            candidates.append(p)
    if DOCS_DIR.exists():
        for p in sorted(DOCS_DIR.glob("*.md")):
            if not _is_historical(p):
                candidates.append(p)
    examples_dir = REPO_ROOT / "examples"
    for p in sorted(examples_dir.glob("*/README.md")):
        candidates.append(p)
    return candidates


def _extract_links_skipping_fences(md_text: str) -> list[tuple[str, str]]:
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


class TestNoBrokenInternalLinks(unittest.TestCase):
    """v0.10 RC: across the entire current-surface doc set, every
    relative-path link must resolve to a real file or directory.

    Builds on the v0.8 docs/README-only link checker; expands the
    coverage to every current-surface md file.
    """

    def test_no_broken_relative_links_anywhere_current_surface(self):
        broken: list[str] = []
        for md_path in _current_surface_md_files():
            text = md_path.read_text(encoding="utf-8")
            for link_text, link_path in _extract_links_skipping_fences(text):
                if _is_external_or_anchor(link_path):
                    continue
                target = _resolve_link(md_path, link_path)
                if not target.exists():
                    broken.append(
                        f"{md_path.relative_to(REPO_ROOT)}: "
                        f"[{link_text}]({link_path}) → "
                        f"{target}")
        self.assertFalse(
            broken,
            "Broken current-surface internal links (v0.10 RC):\n  "
            + "\n  ".join(broken))


if __name__ == "__main__":
    unittest.main()
