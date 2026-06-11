"""Version-string drift guard (one version, four places).

pyproject.toml is the canonical source; `agent_harness_lab.__version__` and the
version claims in both READMEs must agree with it. v0.10 fixed exactly this
drift once and it regressed — so the agreement is pinned by tests, not by
discipline.
"""
import re
import unittest
from pathlib import Path

import agent_harness_lab

ROOT = Path(__file__).resolve().parents[1]

# any backtick-quoted x.y.z[suffix] token is a version claim (plain "3.10"-style
# interpreter ranges have no patch part and are intentionally not matched)
_VERSION_CLAIM_RE = re.compile(r"`(\d+\.\d+\.\d+[^`]*)`")


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    assert m, "pyproject.toml has no `version = \"...\"` line"
    return m.group(1)


class TestVersionDrift(unittest.TestCase):
    def test_package_version_matches_pyproject(self):
        self.assertEqual(agent_harness_lab.__version__, _pyproject_version())

    def _assert_readme_claims_canonical(self, readme_name: str):
        canonical = _pyproject_version()
        text = (ROOT / readme_name).read_text(encoding="utf-8")
        claims = _VERSION_CLAIM_RE.findall(text)
        self.assertIn(canonical, claims,
                      f"{readme_name} does not state the canonical version `{canonical}`")
        stale = sorted(set(claims) - {canonical})
        self.assertEqual(stale, [],
                         f"{readme_name} still claims stale version(s): {stale}")

    def test_readme_en_matches_pyproject(self):
        self._assert_readme_claims_canonical("README.md")

    def test_readme_zh_matches_pyproject(self):
        self._assert_readme_claims_canonical("README.zh-CN.md")


if __name__ == "__main__":
    unittest.main()
