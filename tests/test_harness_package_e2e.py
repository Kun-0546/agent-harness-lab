"""CLI E2E acceptance for v0.5 Harness Package MVP.

Full product flow exercised via subprocess invocations:
ahl init → ahl new --mode manual → write runtime-sources / package / variants
→ ahl run → ahl score → ahl compare. Asserts snapshot.harness_package block,
score evidence with package reasons, compare ## Evidence section.

Also: negative test that variant with `harness_package` but no `runtime_source`
fails CLI run with WorkflowError mentioning the requirement.

These tests spawn real subprocesses (Python agent script, ahl CLI). They use
the stub simulator (single-turn conversations) for determinism.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"

# Minimal deterministic CLI agent (matches connect.md `外部命令行` protocol)
_AGENT_SCRIPT = """#!/usr/bin/env python3
import json, sys
for s in (sys.stdin, sys.stdout):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8")
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    out = {"response": "ack:" + msg.get("input", "")}
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\\n")
    sys.stdout.flush()
"""


def _env() -> dict:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(SRC_PATH)
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def _run_cli(workspace: Path, *args: str, expect_exit: int = 0,
              timeout: int = 60) -> subprocess.CompletedProcess:
    """Invoke `python -m agent_harness_lab <args>` in workspace."""
    r = subprocess.run(
        [sys.executable, "-m", "agent_harness_lab", *args],
        cwd=workspace, env=_env(), text=True,
        capture_output=True, encoding="utf-8", timeout=timeout,
    )
    assert r.returncode == expect_exit, (
        f"`ahl {' '.join(args)}` expected exit {expect_exit}, got "
        f"{r.returncode}\nstdout: {r.stdout!r}\nstderr: {r.stderr!r}"
    )
    return r


def _write_program(exp_dir: Path, assumption: str = "test"):
    """Write a fully-filled program.md so preflight passes."""
    (exp_dir / "program.md").write_text(
        f"""# program

## 假设
{assumption}

## 声明
- 环境:无
- 对话模式:模拟
- 状态:重置
- 评分:LLM
- 运行模式:人评
""", encoding="utf-8")


def _write_rubric(exp_dir: Path):
    (exp_dir / "rubric.md").write_text(
        "# rubric\n\n## quality\n权重: 1.0\n质量\n", encoding="utf-8")


def _write_case(exp_dir: Path, case_id: str = "C1", opening: str = "hello"):
    (exp_dir / "cases" / f"{case_id}.md").write_text(
        f"---\nid: {case_id}\n---\n## 起始输入\n{opening}\n",
        encoding="utf-8")


def _write_runtime_source(workspace: Path, runtime_dir: Path,
                            name: str = "local-tiny"):
    (workspace / "runtime-sources.md").write_text(
        f"# sources\n\n## {name}\ntype: local_path\npath: {runtime_dir}\n",
        encoding="utf-8")


def _write_package(workspace: Path, pkg_id: str, version: str,
                    payload: dict[str, str], env: str = "",
                    start_command: str | None = "python agent.py",
                    runtime_compat: str = "[local_path, git_repo]") -> Path:
    """Write harness-packages/<id>/<version>/{manifest.md, payload/...}."""
    pkg_dir = workspace / "harness-packages" / pkg_id / version
    (pkg_dir / "payload").mkdir(parents=True, exist_ok=True)
    files_decl = ""
    if payload:
        for name, content in payload.items():
            (pkg_dir / "payload" / name).write_text(content,
                                                     encoding="utf-8")
        files_decl = "files:\n" + "\n".join(
            f"  - target: pkg/{n}\n    source: payload/{n}"
            for n in payload
        ) + "\n"
    env_decl = f"env:\n  {env}\n" if env else ""
    start_decl = f"start_command: {start_command}\n" if start_command else ""
    body = f"""---
id: {pkg_id}
version: {version}
runtime_compatibility: {runtime_compat}
---

## Description
E2E acceptance test package.

## Payload

{files_decl}{env_decl}{start_decl}"""
    (pkg_dir / "manifest.md").write_text(body, encoding="utf-8")
    return pkg_dir / "manifest.md"


def _setup_runtime(workspace: Path) -> Path:
    """Write minimal local runtime with agent.py implementing the CLI protocol."""
    runtime = workspace / "tiny-runtime"
    runtime.mkdir()
    (runtime / "agent.py").write_text(_AGENT_SCRIPT, encoding="utf-8")
    return runtime


# ===========================================================================
# Group: Full CLI E2E (positive path)
# ===========================================================================


class TestCliE2EFullFlow(unittest.TestCase):
    """Spec acceptance: ahl init → new → run → score → compare end-to-end."""

    def test_full_product_flow_with_and_without_package(self):
        with TemporaryDirectory() as t:
            ws = Path(t)
            python_quoted = f'"{sys.executable}"'

            # 1. ahl init
            _run_cli(ws, "init")

            # 2. ahl new package-demo --mode manual
            _run_cli(ws, "new", "package-demo", "--mode", "manual")
            exp_dir = ws / "experiments" / "001-package-demo"
            self.assertTrue(exp_dir.exists())

            # 3. minimal local runtime
            runtime = _setup_runtime(ws)
            # 4. runtime-sources.md
            _write_runtime_source(ws, runtime, name="local-tiny")

            # 5. harness package with start_command using sys.executable
            _write_package(
                ws, "test-pkg", "0.1.0",
                payload={"system.md": "PKG STRICT PROMPT\n"},
                env='HARNESS_TEST: "smoke"',
                start_command=f'{python_quoted} agent.py',
            )

            # 6. V1 baseline (no package); V2 with package
            (exp_dir / "harnesses" / "V1.md").write_text(f"""---
id: V1
基线: 是
runtime_source: local-tiny
---

## 这是什么
baseline without package

## Patch

start_command: {python_quoted} agent.py
""", encoding="utf-8")

            (exp_dir / "harnesses" / "V2.md").write_text("""---
id: V2
基线: 否
runtime_source: local-tiny
harness_package: test-pkg@0.1.0
---

## 这是什么
variant with package (no ## Patch — manifest supplies start_command)
""", encoding="utf-8")

            # 7. program.md + rubric.md + case
            _write_program(exp_dir, "package acceptance test")
            _write_rubric(exp_dir)
            _write_case(exp_dir, "C1", "hello")

            # 8. ahl run
            run_result = _run_cli(ws, "run", "001-package-demo", timeout=120)
            self.assertIn("V1", run_result.stdout)
            self.assertIn("V2", run_result.stdout)

            # 9. ahl score
            score_result = _run_cli(ws, "score", "001-package-demo")
            self.assertIn("V1", score_result.stdout)
            self.assertIn("V2", score_result.stdout)

            # 10. ahl compare
            compare_result = _run_cli(ws, "compare", "001-package-demo")

            # ---- ASSERT: snapshot harness_package block ----
            snap_root = exp_dir / "results" / "snapshots"
            self.assertTrue(snap_root.exists())
            run_subdirs = list(snap_root.iterdir())
            self.assertEqual(len(run_subdirs), 1,
                             f"expected 1 run subdir, got {run_subdirs}")
            run_subdir = run_subdirs[0]

            v2_snap_path = run_subdir / "V2.json"
            self.assertTrue(v2_snap_path.exists())
            v2_snap = json.loads(v2_snap_path.read_text(encoding="utf-8"))
            hp = v2_snap.get("harness_package")
            self.assertIsNotNone(hp,
                                  f"V2 snapshot missing harness_package: "
                                  f"{v2_snap}")
            self.assertEqual(hp["id"], "test-pkg")
            self.assertEqual(hp["version"], "0.1.0")
            self.assertEqual(hp["ref"], "test-pkg@0.1.0")
            self.assertTrue(hp["manifest_hash"].startswith("sha256:"))
            self.assertTrue(hp["payload_hash"].startswith("sha256:"))
            self.assertTrue(hp["effective_harness_hash"].startswith("sha256:"))
            self.assertEqual(hp["install_order"], ["package", "patch"])

            # V1 snapshot should have harness_package: null
            v1_snap_path = run_subdir / "V1.json"
            self.assertTrue(v1_snap_path.exists())
            v1_snap = json.loads(v1_snap_path.read_text(encoding="utf-8"))
            self.assertIsNone(v1_snap.get("harness_package"))

            # ---- ASSERT: score evidence for packaged variant ----
            score_files = sorted(
                (exp_dir / "results").glob("score-*.json"))
            self.assertEqual(len(score_files), 1)
            score_data = json.loads(
                score_files[-1].read_text(encoding="utf-8"))
            self.assertIn("evidence", score_data)
            ev_variants = score_data["evidence"]["variants"]
            self.assertIn("V2", ev_variants)
            v2_ev = ev_variants["V2"]
            self.assertEqual(v2_ev["level"], "strong",
                             f"V2 evidence not strong: {v2_ev}")
            joined_reasons = " ".join(v2_ev["reasons"])
            self.assertTrue(
                "test-pkg" in joined_reasons
                or "harness_package" in joined_reasons,
                f"V2 reasons should mention package: {v2_ev['reasons']}")

            # V1 is materialized local_path without package — should be strong v0.4
            v1_ev = ev_variants["V1"]
            self.assertEqual(v1_ev["level"], "strong")
            # V1 reasons should NOT mention harness_package
            for r in v1_ev["reasons"]:
                self.assertNotIn("harness_package", r)

            # ---- ASSERT: compare ## Evidence section ----
            compare_files = sorted(
                (exp_dir / "results").glob("compare-*.md"))
            self.assertEqual(len(compare_files), 1)
            compare_text = compare_files[-1].read_text(encoding="utf-8")
            self.assertIn("## Evidence", compare_text)
            # Mentions package somewhere (test-pkg id or harness_package keyword)
            self.assertTrue(
                "test-pkg" in compare_text or "harness_package" in compare_text,
                f"compare report should mention package: {compare_text[:500]}")

            # ---- ASSERT: no default-created evidence files ----
            materials = exp_dir / "materials"
            if materials.exists():
                for f in ("runtime-evidence.md", "harness-evidence.md",
                          "cloud-evidence.md"):
                    self.assertFalse(
                        (materials / f).exists(),
                        f"unexpected default-created evidence file: {f}")


# ===========================================================================
# Group: Negative CLI flow
# ===========================================================================


class TestCliE2ENegativePackageRequiresRuntimeSource(unittest.TestCase):
    """Spec ERR-VARIANT-2 via CLI: package without runtime_source → ahl run fails."""

    def test_run_fails_when_package_without_runtime_source(self):
        with TemporaryDirectory() as t:
            ws = Path(t)
            python_quoted = f'"{sys.executable}"'

            _run_cli(ws, "init")
            _run_cli(ws, "new", "bad-demo", "--mode", "manual")
            exp_dir = ws / "experiments" / "001-bad-demo"

            # Need a connect.md for V1 baseline (legacy path), since V1 has no runtime_source.
            (ws / "connect.md").write_text("""# connect

## 类型
外部命令行

## 配置
命令:""" + f"{python_quoted} agent.py" + "\n", encoding="utf-8")

            # Also need agent.py somewhere reachable — put it in workspace
            (ws / "agent.py").write_text(_AGENT_SCRIPT, encoding="utf-8")

            # Package (so the ref resolves, not ERR-RESOLV-1)
            _write_package(
                ws, "test-pkg", "0.1.0",
                payload={"a.md": "x"},
                start_command=f"{python_quoted} agent.py",
            )

            # V1 legacy baseline (uses connect.md), no runtime_source, no package
            (exp_dir / "harnesses" / "V1.md").write_text("""---
id: V1
基线: 是
---

## 这是什么
legacy baseline
""", encoding="utf-8")

            # V2 — THE BAD CASE: harness_package set, no runtime_source
            (exp_dir / "harnesses" / "V2.md").write_text("""---
id: V2
基线: 否
harness_package: test-pkg@0.1.0
---

## 这是什么
BAD: package without runtime_source — must fail preflight

## Patch
start_command: cmd
""", encoding="utf-8")

            _write_program(exp_dir, "negative test")
            _write_rubric(exp_dir)
            _write_case(exp_dir, "C1", "hello")

            # Expect non-zero exit
            r = subprocess.run(
                [sys.executable, "-m", "agent_harness_lab",
                 "run", "001-bad-demo"],
                cwd=ws, env=_env(), text=True,
                capture_output=True, encoding="utf-8", timeout=60,
            )
            self.assertNotEqual(r.returncode, 0,
                                f"expected non-zero exit;\n"
                                f"stdout: {r.stdout!r}\nstderr: {r.stderr!r}")
            combined = (r.stdout or "") + (r.stderr or "")
            # ERR-VARIANT-2 message mentions runtime_source requirement
            self.assertTrue(
                "必须同时指定 runtime_source" in combined
                or "runtime_source" in combined,
                f"error message should mention runtime_source requirement: "
                f"{combined!r}"
            )


if __name__ == "__main__":
    unittest.main()
